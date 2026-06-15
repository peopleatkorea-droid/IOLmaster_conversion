IOLMaster 700 CSV Converter - 전공의용 사용법
=============================================

[전공의 사용법]
1. IOLMasterParser.exe를 더블클릭합니다.
2. [CSV 선택]을 누르고 IOLMaster 700 Export CSV 파일을 고릅니다.
3. [변환 시작]을 누릅니다.
4. 저장할 XLSX 파일 이름을 선택합니다.
5. 완료 메시지가 뜨면 생성된 XLSX 파일을 Excel에서 열어 확인합니다.

주의사항
- CSV 파일 형식은 ZEISS IOLMaster 700 Export 형식이어야 합니다.
- Pat_ID는 앞자리 0이 사라지지 않도록 텍스트로 저장됩니다.
- 변환할 CSV나 저장할 XLSX 파일이 Excel에서 열려 있으면 저장 오류가 날 수 있습니다.
- 오류가 나면 사용자 폴더의 IOLMasterParser_error.txt를 개발자에게 보내 주세요.

[개발자/관리자 빌드 방법]
Windows PC에서만 EXE 빌드를 권장합니다.

1. Python 3.9 이상 설치
   - python.org에서 설치
   - 설치 시 'Add python.exe to PATH' 또는 py launcher 사용 가능하게 설정

2. 이 폴더에서 build_windows.bat 더블클릭

3. 빌드가 끝나면 아래 파일이 생성됩니다.
   dist\IOLMasterParser.exe

4. 전공의에게는 dist\IOLMasterParser.exe 하나만 보내면 됩니다.

배포 팁
- 병원 PC 보안 때문에 처음 실행 시 Windows SmartScreen 경고가 뜰 수 있습니다.
- 가능하면 병원 내부 공유폴더/인트라넷/공식 이메일로 배포하세요.
- 배포 전 샘플 CSV 1개로 정상 변환 여부와 Pat_ID 앞자리 0 보존 여부를 꼭 확인하세요.
