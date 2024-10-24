import os
import boto3
import base64
import pymysql.cursors
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from ultralytics import YOLO
from PIL import Image
from werkzeug.utils import secure_filename
from io import BytesIO

# 모델 로드
model = YOLO("./models/best30_16.pt")

app = Flask(__name__)
CORS(app, supports_credentials=True)

# AWS 설정
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
    region_name='ap-northeast-2'
)

# MySQL 연결 설정
def get_db_connection():
    connection = pymysql.connect(
        host=os.environ.get('DB_HOST'),  
        port=3306,
        user=os.environ.get('DB_USER'),  
        password=os.environ.get('DB_PASSWORD'), 
        db=os.environ.get('DB_NAME'),  
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    return connection

s3_url=os.environ.get('S3_URL')
print(s3_url)

@app.route('/predict', methods=['POST'])
def predict():
    if 'image0' not in request.files:
        return jsonify({"error": "No image file found in request"}), 400
    
    chat_id = request.form.get('chat_id') #채팅방 번호
    
    # 업로드된 파일들 처리
    for key in request.files:
        file = request.files[key]
        
        # 이미지를 디코딩하기 위해 BytesIO로 변환
        file_data = file.read()  # 파일 바이너리 데이터 읽기
        img_stream = BytesIO(file_data)  # BytesIO로 변환
        img = Image.open(img_stream)  # 디코딩된 이미지 열기
        
        # 이미지 후 예측 수행
        results = model(img)

        # 결과를 JSON 형식으로 변환
        results_json = results[0].tojson()
        name = get_names_from_results(results_json)
        print(name)
        
        filename = secure_filename(file.filename)
        
        s3_file_path = f'pill_images/{chat_id}/{filename}'
        
        try:
            img_stream.seek(0)
            s3_client.upload_fileobj(
                img_stream,  # 디코딩된 이미지 스트림
                'moyak-bucket',
                s3_file_path,
                ExtraArgs={'ACL': 'public-read', "ContentType": file.content_type}
            )
            
            image_url = f'https://{s3_url}/{s3_file_path}'
            
            transformed_name = transform_name(name)
            print(transformed_name)
        
            add_eachpill(chat_id, transformed_name, image_url)
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        
    
    return jsonify({'message': '파일 업로드 성공', 'image_url': image_url, "chat_id" : chat_id}), 200    
        
# 이름을 변환하는 함수
def transform_name(name):
    name_dict = {
        'AW': {'pill_id': 'AW', 'pill_name': '노르믹스정', 'pill_ingredient': 'Rifaximin 200mg'},
        'BL2': {'pill_id': 'BL2', 'pill_name': '베아렌투엑스정', 'pill_ingredient': 'Artemisia Herb 95% Ethanol Soft Ext.(20→1) 90mg'},
        'DCE': {'pill_id': 'DCE', 'pill_name': '동구에페리손정', 'pill_ingredient': 'Eperisone Hydrochloride 50mg'},
        'GM': {'pill_id': 'GM', 'pill_name': '가스몬정', 'pill_ingredient': 'Mosapride Citrate Hydrate 5.29mg'},
        'HCS_HWPB': {'pill_id': 'HCS_HWP', 'pill_name': '하이퍼셋세미정', 'pill_ingredient': 'Acetaminophen 162.5mg, Tramadol Hydrochloride 18.75mg'},
        'HCS_HWPF': {'pill_id': 'HCS_HWP', 'pill_name': '하이퍼셋세미정', 'pill_ingredient': 'Acetaminophen 162.5mg, Tramadol Hydrochloride 18.75mg'},
        'HN': {'pill_id': 'HN', 'pill_name': '티파스정', 'pill_ingredient': 'Tiropramide Hydrochloride 100mg'},
        'HNT1F': {'pill_id': 'HNT1', 'pill_name': '트리원정', 'pill_ingredient': 'Trimebutine Maleate 100mg'},
        'HNT1B': {'pill_id': 'HNT1', 'pill_name': '트리원정', 'pill_ingredient': 'Trimebutine Maleate 100mg'},
        'MKFC': {'pill_id': 'MKFC', 'pill_name': '페노클정', 'pill_ingredient': 'Aceclofenac 100mg'},
        'N1KBB': {'pill_id': 'N1KB', 'pill_name': '엔클로페낙정', 'pill_ingredient': 'Aceclofenac 100mg'},
        'N1KBF': {'pill_id': 'N1KB', 'pill_name': '엔클로페낙정', 'pill_ingredient': 'Aceclofenac 100mg'},
        'PNX': {'pill_id': 'PNX', 'pill_name': '뮤페리손SR서방정', 'pill_ingredient': 'Eperisone Hydrochloride 75mg'}
    }
    
    # 사전에 해당 이름이 있으면 변환된 딕셔너리를 반환, 없으면 기본값 반환
    return name_dict.get(name, {'pill_id': name, 'pill_name': 'Unknown', 'pill_ingredient': 'Unknown'})

# name 파싱 함수
def get_names_from_results(results_json):
    results_dict = json.loads(results_json) # JSON 문자열을 Python 객체로 변환
    name = [item.get('name') for item in results_dict if 'name' in item] # name 필드만 추출
    return (''.join(name))

# EachPill 테이블에 알약 정보 추가하는 함수
def add_eachpill(chat_id, transformed_name, image_url):

    pill_name = transformed_name['pill_name'] #알약 이름
    pill_ingredient = transformed_name['pill_ingredient'] #알약 성분

    print("111111."+image_url)
    
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "INSERT INTO EachPill (chat_id, image, pill_name, pill_ingredient) VALUES (%s, %s, %s, %s)"
            cursor.execute(sql, (chat_id, image_url, pill_name, pill_ingredient))
            connection.commit()
    finally:
        connection.close()

if __name__ == '__main__':
    app.run(debug=True)