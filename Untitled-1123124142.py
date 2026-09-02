import streamlit as st
import pandas as pd
import base64
import folium
from streamlit_folium import st_folium
from supabase import create_client
requests = __import__('requests')
import uuid
import os

# Supabase 연결 설정
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()
BUCKET_NAME = "Map image"  # 스토리지 버킷 이름

st.title("🗺️ 순천시 청년 맛집 지도")

tab1, tab2, tab3 = st.tabs(["청년맛집 제보하기", "청년맛집 지도보기", "관리자 페이지"])

# Supabase Storage에 이미지 업로드 함수 (한글/특수문자 파일명 에러 방지용 UUID 적용)
def upload_image_to_supabase(file, store_name):
    try:
        file_bytes = file.getvalue()
        
        # 파일 확장자 추출 (.jpg, .png 등)
        file_extension = os.path.splitext(file.name)[1]
        if not file_extension:
            file_extension = ".jpg"
            
        # 한글 및 특수문자 에러를 막기 위해 고유한 UUID 영어 파일명으로 변환
        safe_filename = f"{uuid.uuid4()}{file_extension}"
        
        response = supabase.storage.from_(BUCKET_NAME).upload(
            path=safe_filename,
            file=file_bytes,
            file_options={"content-type": file.type, "upsert": "true"}
        )
        
        public_url_res = supabase.storage.from_(BUCKET_NAME).get_public_url(safe_filename)
        return public_url_res
    except Exception as e:
        st.error(f"서버 사진 업로드 중 오류 발생: {e}")
        return None

# 웹 URL 이미지를 Base64로 변환하여 팝업 깨짐 방지
def get_web_image_base64(image_url):
    try:
        response = requests.get(image_url)
        if response.status_code == 200:
            encoded = base64.b64encode(response.content).decode("utf-8")
            return f"data:image/jpeg;base64,{encoded}"
    except:
        pass
    return ""

def load_data():
    response = supabase.table("restaurants").select("*").execute()
    if response.data:
        return pd.DataFrame(response.data)
    else:
        return pd.DataFrame(columns=["id", "name", "address", "lat", "lng", "review", "images", "status"])

# 1. 사용자 제보 탭
with tab1:
    st.subheader("나만의 청년 맛집을 제보해주세요!")
    st.write("💡 지도를 움직여 원하는 위치를 클릭하면 위치가 저장됩니다.")

    if 'selected_lat' not in st.session_state:
        st.session_state.selected_lat = 34.9506
    if 'selected_lng' not in st.session_state:
        st.session_state.selected_lng = 127.4875

    # 선택된 좌표를 중심으로 가볍고 빠르게 지도를 렌더링합니다.
    m_click = folium.Map(
        location=[st.session_state.selected_lat, st.session_state.selected_lng], 
        zoom_start=14,
        prefer_canvas=True
    )
    folium.Marker(
        [st.session_state.selected_lat, st.session_state.selected_lng],
        popup="선택된 가게 위치",
        icon=folium.Icon(color="blue", icon="info-sign")
    ).add_to(m_click)
    
    # 💡 성능 최적화: 클릭 이벤트("last_clicked")만 단독으로 받아오도록 변경하여 씹힘 및 버벅임 완전 해소
    map_data = st_folium(
        m_click, 
        width=700, 
        height=450, 
        key="submission_map",
        returned_objects=["last_clicked"]
    )

    # 지도를 클릭했을 때만 즉시 좌표를 갱신하고 화면을 다시 그려 마커를 옮깁니다.
    if map_data and map_data.get("last_clicked"):
        clicked_lat = map_data["last_clicked"]["lat"]
        clicked_lng = map_data["last_clicked"]["lng"]
        if st.session_state.selected_lat != clicked_lat or st.session_state.selected_lng != clicked_lng:
            st.session_state.selected_lat = clicked_lat
            st.session_state.selected_lng = clicked_lng
            st.rerun()

    st.success(f"📌 현재 선택된 위치 (`{st.session_state.selected_lat:.6f}`, `{st.session_state.selected_lng:.6f}`)")

    with st.form("user_form"):
        store_name = st.text_input("가게 이름")
        store_address = st.text_input("가게 주소 (예: 순천시 장명로 30)")
        store_review = st.text_area("추천 이유 / 리뷰 (선택)")
        
        uploaded_files = st.file_uploader(
            "가게 사진 첨부 (선택, 최대 3장)", 
            type=["png", "jpg", "jpeg"], 
            accept_multiple_files=True
        )
        
        submitted = st.form_submit_button("제보하기")
        
        if submitted:
            if not store_name:
                st.error("가게 이름은 필수 입력입니다!")
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
                    "status": "Pending"
                }).execute()
                
                st.success(f"'{store_name}' 제보가 완료되었습니다! 관리자 검토 후 등록됩니다.")

# 2. 지도 보기 탭
with tab2:
    st.subheader("📍 순천시 청년 맛집 지도")
    st.write("순천시 청년들의 추천을 받은 맛집들입니다!")
    
    df = load_data()
    if not df.empty and 'status' in df.columns:
        approved_df = df[df['status'] == 'Approved']
    else:
        approved_df = pd.DataFrame()
    
    suncheon_lat, suncheon_lng = 34.9506, 127.4875
    m = folium.Map(location=[suncheon_lat, suncheon_lng], zoom_start=13, prefer_canvas=True)
    
    if approved_df.empty:
        st.info("현재 지도에 등록된 승인 맛집이 없습니다. 관리자 페이지에서 제보를 승인해주세요!")
    else:
        for _, row in approved_df.iterrows():
            img_tag = ""
            imgs = str(row['images'])
            if imgs != "없음" and imgs != "nan" and imgs != "":
                urls = imgs.split(",")
                if urls:
                    b64_img = get_web_image_base64(urls[0])
                    if b64_img:
                        img_tag = f'<img src="{b64_img}" style="width: 80px; height: 80px; object-fit: cover; border-radius: 6px; margin-left: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.2);">'

            popup_html = f"""
            <div style="width: 280px; font-family: 'Malgun Gothic', sans-serif; padding: 4px;">
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
                tooltip=row['name'],
                icon=folium.Icon(color="red", icon="cutlery", prefix="fa")
            ).add_to(m)
            
    st_folium(m, width=700, height=500, key="view_map", returned_objects=[])

# 3. 관리자 페이지 탭
with tab3:
    st.subheader("🔐 관리자 검토 페이지")
    password = st.text_input("관리자 비밀번호를 입력하세요", type="password", key="admin_pw")
    
    if password == "6230":
        st.success("관리자 로그인 성공!")
        df = load_data()
        
        if df.empty:
            st.write("저장된 제보가 없습니다.")
        else:
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
                            st.markdown(f"**{row['name']}**")
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
                                st.success(f"'{row['name']}' 승인 완료!")
                                st.rerun()
                                
                            if st.button("❌ 반려/삭제", key=f"p_del_{row_id}"):
                                supabase.table("restaurants").delete().eq("id", row_id).execute()
                                st.warning("제보가 삭제되었습니다.")
                                st.rerun()
                        st.divider()
                        
            st.markdown("---")
            st.write(f"### ✅ 승인 완료된 맛집 목록 ({len(approved_df)}건)")
            
            if approved_df.empty:
                st.write("승인된 맛집이 없습니다.")
            else:
                for idx, row in approved_df.iterrows():
                    row_id = row['id']
                    with st.container():
                        col1, col2 = st.columns([4, 1])
                        with col1:
                            st.markdown(f"**{row['name']}** (등록 완료됨)")
                            st.write(f"주소: {row['address']} (위도: {row['lat']}, 경도: {row['lng']})")
                        with col2:
                            if st.button("등록 취소(삭제)", key=f"a_del_{row_id}"):
                                supabase.table("restaurants").delete().eq("id", row_id).execute()
                                st.warning("등록이 취소되었습니다.")
                                st.rerun()
                        st.divider()
                        
    elif password != "":
        st.error("비밀번호가 틀렸습니다.")