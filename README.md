# M365 File Portal

Azure App Service for Linux에서 실행하는 Python Flask 웹 앱입니다.

- App Service Authentication(Easy Auth)으로 Microsoft Entra ID 로그인 강제
- System-assigned Managed Identity로 Azure Blob Storage 접근
- 사용자 Object ID별 Blob 경로 분리
- 파일 목록, 업로드, 다운로드, 삭제
- 기본 업로드 제한 50MB

## 1. Azure 리소스

1. Linux App Service를 Python 3.12 런타임으로 생성합니다.
2. Storage Account와 private Blob container `uploads`를 생성합니다.
3. App Service의 **Identity > System assigned**를 On으로 설정합니다.
4. Storage Account 또는 container의 **Access control (IAM)**에서 App Service Managed Identity에 **Storage Blob Data Contributor**를 부여합니다.

## 2. App Service 환경 변수

**Settings > Environment variables**에 추가합니다.

- `STORAGE_ACCOUNT_NAME`: Storage Account 이름
- `BLOB_CONTAINER_NAME`: `uploads`
- `FLASK_SECRET_KEY`: 충분히 긴 임의 문자열
- `MAX_UPLOAD_MB`: `50`
- `ALLOWED_EXTENSIONS`: `txt,pdf,png,jpg,jpeg,csv,xlsx,docx,pptx,zip`

## 3. 시작 명령

**Configuration > General settings > Startup Command**:

`gunicorn --bind=0.0.0.0:8000 --timeout 600 app:app`

## 4. Microsoft Entra ID 로그인

App Service의 **Authentication > Add identity provider > Microsoft**에서 새 App Registration을 만들고 다음을 설정합니다.

- Require authentication
- Unauthenticated requests: HTTP 302 redirect
- Tenant restriction: 현재 조직 tenant(single tenant)

Easy Auth가 앱 요청에 `X-MS-CLIENT-PRINCIPAL-NAME`과 `X-MS-CLIENT-PRINCIPAL-ID`를 전달합니다.

## 5. GitHub Actions OIDC

GitHub repository의 **Settings > Secrets and variables > Actions**에서 다음 secret을 만듭니다.

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

Variables에는 다음을 만듭니다.

- `AZURE_WEBAPP_NAME`: App Service 이름

Azure 쪽 Federated Credential과 배포용 identity 권한은 App Service **Deployment Center**에서 GitHub Actions와 User-assigned identity/OIDC를 선택해 자동 구성하는 방법이 가장 간단합니다. 자동 생성 workflow를 사용한다면 이 저장소의 `deploy.yml`과 중복 실행되지 않도록 하나만 유지합니다.

## 6. 배포

모든 파일을 GitHub repository의 root에 올리고 `main` branch로 push합니다. `package.json`이나 npm 단계는 필요하지 않습니다.

## 7. 검증

1. App Service URL 접속 시 Microsoft 로그인으로 이동하는지 확인합니다.
2. 로그인 후 파일을 업로드합니다.
3. Storage container에서 `{Entra Object ID}/파일명` 형태의 Blob을 확인합니다.
4. 목록, 다운로드, 삭제를 확인합니다.
5. `/health`가 `{"status":"ok"}`를 반환하는지 확인합니다.

## 주의

- Easy Auth를 `Require authentication`으로 설정하지 않으면 앱의 로컬 fallback 사용자 경로가 사용될 수 있습니다.
- Storage Account Key 또는 connection string을 코드나 GitHub에 저장하지 마세요.
- Storage firewall 또는 Private Endpoint를 사용하면 App Service VNet Integration과 DNS 구성이 추가로 필요합니다.
- 대용량 파일은 현재 메모리 기반 다운로드 대신 스트리밍 또는 짧은 수명의 User Delegation SAS 방식으로 확장하는 것이 좋습니다.
