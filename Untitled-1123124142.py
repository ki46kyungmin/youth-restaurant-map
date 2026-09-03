import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from supabase import create_client
import uuid
import os
import time

@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()
BUCKET_NAME = "Map image"

if 'rotation_active' not in st.session_state:
    st.session_state.rotation_active = False
if 'rotation_interval' not in st.session_state:
    st.session_state.rotation_interval = 3
if 'rotation_index' not in st.session_state:
    st.session_state.rotation_index = 0
if 'active_tab_index' not in st.session_state:
    st.session_state.active_tab_index = 0

st.markdown("""
    <style>
    @media (max-width: 768px) {
        .responsive-title {
            font-size: 1.6rem !important;
        }
    }
    </style>
    <h1 class="responsive-title" style="font-size: 2.2rem; font-weight: bold; margin-bottom: 20px;">
        🗺️ 순천시 청년 공간 및 맛집 지도
    </h1>
""", unsafe_allow_html=True)

# 탭 상태가 새로고침 시 풀리지 않도록 세션 인덱스 연동
tab_titles = ["청년 공간 제보하기", "청년 공간 지도보기", "관리자 페이지"]
selected_tab = st.radio("메뉴", tab_titles, index=st.session_state.active_tab_index, horizontal=True, label_visibility="collapsed")

if selected_tab == "청년 공간 제보하기":
    st.session_state.active_tab_index = 0
elif selected_tab == "청년 공간 지도보기":
    st.session_state.active_tab_index = 1
elif selected_tab == "관리자 페이지":
    st.session_state.active_tab_index = 2

def upload_image_to_supabase(file, store_name):
    try:
        file_bytes = file.getvalue()
        file_extension = os.path.splitext(file.name)[1]
        if not file_extension:
            file_extension = ".jpg"
            
        safe_filename = f"{uuid.uuid4()}{file_extension}"
        
        supabase.storage.from_(BUCKET_NAME).upload(
            path=safe_filename,
            file=file_bytes,
            file_options={"content-type": file.type, "upsert": "true"}
        )
        
        public_url_res = supabase.storage.from_(BUCKET_NAME).get_public_url(safe_filename)
        return public_url_res
    except Exception as e:
        st.error(f"서버 사진 업로드 중 오류 발생: {e}")
        return None

@st.cache_data(ttl=60)
def load_data():
    response = supabase.table("restaurants").select("*").execute()
    if response.data:
        return pd.DataFrame(response.data)
    else:
        return pd.DataFrame(columns=["id", "name", "address", "lat", "lng", "review", "images", "status", "category"])

CATEGORY_ICONS = {
    "맛집": {"color": "red", "icon": "cutlery"},
    "공유공간": {"color": "blue", "icon": "users"},
    "문화공간": {"color": "purple", "icon": "paint-brush"},
    "추천관광지": {"color": "green", "icon": "tree"}
}

if selected_tab == "청년 공간 제보하기":
    st.subheader("나만의 청년 공간/맛집을 제보해주세요!")
    st.write("💡 지도를 움직여 원하는 위치를 클릭하면 위치가 저장됩니다.")

    if 'selected_lat' not in st.session_state:
        st.session_state.selected_lat = 34.9506
    if 'selected_lng' not in st.session_state:
        st.session_state.selected_lng = 127.4875

    m_click = folium.Map(
        location=[st.session_state.selected_lat, st.session_state.selected_lng], 
        zoom_start=14,
        prefer_canvas=True
    )
    folium.Marker(
        [st.session_state.selected_lat, st.session_state.selected_lng],
        popup="선택된 위치",
        icon=folium.Icon(color="orange", icon="info-sign")
    ).add_to(m_click)
    
    map_data = st_folium(
        m_click, 
        use_container_width=True,
        height=330, 
        key="submission_map",
        returned_objects=["last_clicked", "zoom"]
    )

    if map_data and map_data.get("last_clicked"):
        clicked_lat = map_data["last_clicked"]["lat"]
        clicked_lng = map_data["last_clicked"]["lng"]
        if st.session_state.selected_lat != clicked_lat or st.session_state.selected_lng != clicked_lng:
            st.session_state.selected_lat = clicked_lat
            st.session_state.selected_lng = clicked_lng
            st.rerun()

    # st.success(f"📌 현재 선택된 위치 (`{st.session_state.selected_lat:.6f}`, `{st.session_state.selected_lng:.6f}`)")

    with st.form("user_form"):
        store_category = st.selectbox("카테고리 선택", ["맛집", "공유공간", "문화공간", "추천관광지"])
        store_name = st.text_input("장소(가게) 이름")
        store_address = st.text_input("주소 (예: 순천시 장명로 30)")
        store_review = st.text_area("추천 이유 / 리뷰 (선택)")
        
        uploaded_files = st.file_uploader(
            "사진 첨부 (선택, 최대 3장)", 
            type=["png", "jpg", "jpeg"], 
            accept_multiple_files=True
        )
        
        submitted = st.form_submit_button("제보하기")
        
        if submitted:
            if not store_name:
                st.error("장소 이름은 필수 입력입니다!")
            elif uploaded_files and len(uploaded_files) > 3:
                st.error("사진은 최대 3장까지만 업로드할 수 있습니다!")
            else:
                image_urls = []
                if uploaded_files:
                    for file in uploaded_files:
                        url = upload_image_to_supabase(file, store_name)
                        if url:
                            image_urls.append(url)
                
                image_str = ",".join(image_urls) if image_urls else "없음"
                review_text = store_review if store_review else "작성된 리뷰 없음"
                lat = st.session_state.selected_lat
                lng = st.session_state.selected_lng
                address_text = store_address if store_address else "주소 미입력"
                
                supabase.table("restaurants").insert({
                    "name": store_name,
                    "address": address_text,
                    "lat": lat,
                    "lng": lng,
                    "review": review_text,
                    "images": image_str,
                    "status": "Pending",
                    "category": store_category
                }).execute()
                
                st.cache_data.clear()
                st.success(f"'{store_name}' 제보가 완료되었습니다! 관리자 검토 후 등록됩니다.")

elif selected_tab == "청년 공간 지도보기":
    st.subheader("📍 순천시 청년 공간 및 맛집 지도")
    st.write("순천시 청년들이 추천하는 다양한 공간들을 확인해보세요!")
    
    df = load_data()
    if not df.empty and 'status' in df.columns:
        approved_df = df[df['status'] == 'Approved'].copy()
    else:
        approved_df = pd.DataFrame()
    
    if not approved_df.empty:
        if 'category' not in approved_df.columns:
            approved_df['category'] = '맛집'
        approved_df['category'] = approved_df['category'].fillna('맛집')

        total_count = len(approved_df)
        cat_counts = approved_df['category'].value_counts()
        
        rotation_status_text = "🟢 작동 중 (실시간 순환 로테이션 중)" if st.session_state.rotation_active else "⚪ 정지됨"
        
        st.markdown(f"""
            <div style="background-color: #f8f9fa; padding: 10px 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e9ecef;">
                <b>📊 등록된 장소 현황</b> <br>
                전체: <b>{total_count}개</b> | 
                🍽️ 맛집: <b>{cat_counts.get('맛집', 0)}개</b> | 
                👥 공유공간: <b>{cat_counts.get('공유공간', 0)}개</b> | 
                🎨 문화공간: <b>{cat_counts.get('문화공간', 0)}개</b> | 
                🌳 추천관광지: <b>{cat_counts.get('추천관광지', 0)}개</b>
            </div>
        """, unsafe_allow_html=True)

        categories_list = ["맛집", "공유공간", "문화공간", "추천관광지"]
        
        if st.session_state.rotation_active:
            current_cat = categories_list[st.session_state.rotation_index % len(categories_list)]
            st.info(f"🔄 자동 순환 중: **[{current_cat}]** 카테고리를 표시하고 있습니다. ({st.session_state.rotation_interval}초 후 다음으로 전환)")
            map_df = approved_df[approved_df['category'] == current_cat]
        else:
            selected_filter = st.selectbox("🔍 카테고리 필터", ["전체보기", "맛집", "공유공간", "문화공간", "추천관광지"])
            if selected_filter != "전체보기":
                map_df = approved_df[approved_df['category'] == selected_filter]
            else:
                map_df = approved_df
    else:
        map_df = pd.DataFrame()
        st.markdown("""
            <div style="background-color: #f8f9fa; padding: 10px 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e9ecef;">
                <b>📊 등록된 장소 현황</b> : 전체 0개 (등록된 장소 없음)
            </div>
        """, unsafe_allow_html=True)
        st.selectbox("🔍 카테고리 필터", ["전체보기", "맛집", "공유공간", "문화공간", "추천관광지"])

    suncheon_lat, suncheon_lng = 34.9506, 127.4875
    m = folium.Map(location=[suncheon_lat, suncheon_lng], zoom_start=13, prefer_canvas=True)
    
    if not map_df.empty:
        for _, row in map_df.iterrows():
            img_tag = ""
            imgs = str(row['images'])
            if imgs != "없음" and imgs != "nan" and imgs != "":
                urls = imgs.split(",")
                if urls and urls[0]:
                    img_tag = f'<img src="{urls[0]}" style="width: 80px; height: 80px; object-fit: cover; border-radius: 6px; margin-left: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.2);">'

            cat_name = row.get('category', '맛집')
            icon_info = CATEGORY_ICONS.get(cat_name, {"color": "red", "icon": "cutlery"})

            popup_html = f"""
            <div style="width: 280px; font-family: 'Malgun Gothic', sans-serif; padding: 4px;">
              <div style="margin-bottom: 4px;"><span style="background-color: #eee; padding: 2px 6px; font-size: 11px; border-radius: 4px; font-weight: bold;">[{cat_name}]</span></div>
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <div style="flex-grow: 1; padding-right: 6px;">
                  <h4 style="margin: 0 0 6px 0; font-size: 15px; font-weight: bold; color: #222;">{row['name']}</h4>
                  <p style="margin: 0; font-size: 12px; color: #555; line-height: 1.4;">{row['address']}</p>
                </div>
                <div>{img_tag}</div>
              </div>
            </div>
            """
            popup = folium.Popup(popup_html, max_width=320)
            folium.Marker(
                [float(row['lat']), float(row['lng'])],
                popup=popup,
                tooltip=f"[{cat_name}] {row['name']}",
                icon=folium.Icon(color=icon_info["color"], icon=icon_info["icon"], prefix="fa")
            ).add_to(m)

    st_folium(m, use_container_width=True, height=500, key="view_map", returned_objects=[])

    if st.session_state.rotation_active and not approved_df.empty:
        time.sleep(st.session_state.rotation_interval)
        st.session_state.rotation_index += 1
        st.rerun()

elif selected_tab == "관리자 페이지":
    st.subheader("🔐 관리자 검토 페이지")
    password = st.text_input("관리자 비밀번호를 입력하세요", type="password", key="admin_pw")
    
    if password == "6230":
        st.success("관리자 로그인 성공!")
        
        st.markdown("---")
        st.subheader("⚙️ 지도 카테고리 실시간 순환(로테이션) 설정")
        st.write("지도의 마커들이 일정 시간마다 카테고리별로 자동 전환되는 로테이션 기능을 제어할 수 있습니다.")
        
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            new_interval = st.slider("순환 주기 (초)", min_value=1, max_value=10, value=st.session_state.rotation_interval)
            if new_interval != st.session_state.rotation_interval:
                st.session_state.rotation_interval = new_interval
        
        with col_r2:
            st.write("### 제어 스위치")
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                if st.button("▶ 순환 시작", use_container_width=True):
                    st.session_state.rotation_active = True
                    st.session_state.rotation_index = 0
                    st.success("로테이션이 시작되었습니다! 지도 탭을 확인하세요.")
                    st.rerun()
            with col_b2:
                if st.button("⏸ 정지하기", use_container_width=True):
                    st.session_state.rotation_active = False
                    st.warning("로테이션이 정지되었습니다.")
                    st.rerun()

        df = load_data()
        
        if df.empty:
            st.write("저장된 제보가 없습니다.")
        else:
            if 'category' not in df.columns:
                df['category'] = '맛집'
            
            pending_df = df[df['status'] == 'Pending']
            approved_df = df[df['status'] == 'Approved']
            
            st.markdown("---")
            st.write(f"### ⏳ 승인 대기 중인 제보 목록 ({len(pending_df)}건)")
            
            if pending_df.empty:
                st.write("대기 중인 제보가 없습니다.")
            else:
                for idx, row in pending_df.iterrows():
                    row_id = row['id']
                    with st.container():
                        col1, col2 = st.columns([3, 2])
                        with col1:
                            st.markdown(f"**[{row['category']}] {row['name']}**")
                            st.write(f"주소: {row['address']}")
                            st.write(f"지정된 위치 (위도: {row['lat']:.6f}, 경도: {row['lng']:.6f})")
                            st.info(f"💬 추천 이유: {row['review']}")
                            
                            imgs = str(row['images'])
                            if imgs != "없음" and imgs != "nan" and imgs != "":
                                urls = imgs.split(",")
                                img_cols = st.columns(len(urls))
                                for img_idx, url in enumerate(urls):
                                    with img_cols[img_idx]:
                                        st.image(url, use_container_width=True, caption=f"사진 {img_idx+1}")
                        
                        with col2:
                            st.write("📌 **위치 미세조정 필요시 직접 수정**")
                            new_lat = st.number_input("위도 (Lat)", value=float(row['lat']), format="%.6f", key=f"lat_{row_id}")
                            new_lng = st.number_input("경도 (Lng)", value=float(row['lng']), format="%.6f", key=f"lng_{row_id}")
                            
                            if st.button("✅ 위치 확인 및 승인하기", key=f"approve_{row_id}"):
                                supabase.table("restaurants").update({
                                    "lat": new_lat,
                                    "lng": new_lng,
                                    "status": "Approved"
                                }).eq("id", row_id).execute()
                                st.cache_data.clear()
                                st.success(f"'{row['name']}' 승인 완료!")
                                st.rerun()
                                
                            if st.button("❌ 반려/삭제", key=f"p_del_{row_id}"):
                                supabase.table("restaurants").delete().eq("id", row_id).execute()
                                st.cache_data.clear()
                                st.warning("제보가 삭제되었습니다.")
                                st.rerun()
                        st.divider()
                        
            st.markdown("---")
            st.write(f"### ✅ 승인 완료된 공간/맛집 목록 ({len(approved_df)}건)")
            
            if approved_df.empty:
                st.write("승인된 항목이 없습니다.")
            else:
                for idx, row in approved_df.iterrows():
                    row_id = row['id']
                    with st.container():
                        col1, col2 = st.columns([4, 1])
                        with col1:
                            st.markdown(f"**[{row['category']}] {row['name']}** (등록 완료됨)")
                            st.write(f"주소: {row['address']} (위도: {row['lat']}, 경도: {row['lng']})")
                        with col2:
                            if st.button("등록 취소(삭제)", key=f"a_del_{row_id}"):
                                supabase.table("restaurants").delete().eq("id", row_id).execute()
                                st.cache_data.clear()
                                st.warning("등록이 취소되었습니다.")
                                st.rerun()
                        st.divider()
                        
    elif password != "":
        st.error("비밀번호가 틀렸습니다.")