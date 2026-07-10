# IOLMaster 700 Biometry Parser

IOLMaster 700 Export CSV를 eye-based XLSX로 변환하고, age-adjusted biometry OOD score를 계산하는 Windows용 무설치 프로그램입니다.

## 전공의 사용법

1. `IOLMasterParser.exe`를 더블클릭합니다.
2. `CSV 선택`을 누르고 IOLMaster 700 Export CSV 파일을 고릅니다.
3. `변환 시작`을 누릅니다.
4. 저장할 XLSX 파일 이름을 선택합니다.
5. 완료 메시지가 뜨면 생성된 XLSX 파일을 Excel에서 열어 확인합니다.

## Biometry OOD 결과

모델 입력은 `Age`, `AL`, `Mean K`, `ACD`, `LT`입니다. `Mean K`는 IOLMaster의 `R1`, `R2`와 keratometric constant 337.5를 이용해 계산합니다. ACD와 LT는 연령에 대한 robust quadratic regression으로 보정한 뒤, 다음 네 변수의 robust Mahalanobis distance를 계산합니다.

```text
AL / Mean K / Age-adjusted ACD / Age-adjusted LT
```

출력 열의 의미는 다음과 같습니다.

```text
OOD_Percentile < 90.0       Anatomy_Score 0: Typical anatomy
90.0 이상, 97.5 미만       Anatomy_Score 1: Uncommon anatomy
97.5 이상                  Anatomy_Score 2: Highly unusual anatomy
```

`OOD_Reference_Context`는 동일 기준군에서 이 정도 이상으로 드문 눈이 대략 몇 안 중 1안인지 표시합니다. `Anatomy_Score`와 `OOD_Distance`는 연구 및 재현성을 위한 기술 지표이며, 웹 화면에서는 접힌 세부정보로만 제공합니다. `OOD_Dominant_Deviation`은 절대 standardized deviation이 큰 두 축을 표시합니다. 이는 Mahalanobis distance의 인과적 분해나 굴절오차 설명이 아닙니다.

현재 `age-stratified-v2.0.0`은 연령에 따라 Pediatric(2–17세), Young adult(18–39세), Adult cataract-age(40–100세)를 자동 선택합니다. WTW와 CCT가 모두 유효하면 Extended, 둘 중 하나라도 없으면 Core를 선택합니다. 해부학적 희귀도를 나타낼 뿐, 굴절 prediction error나 최적 formula를 직접 예측하지 않습니다. 외부 검증과 술후 결과 검증 전에는 임상 의사결정 기준으로 사용하지 마십시오.

## 주의사항

- CSV 파일 형식은 ZEISS IOLMaster 700 Export 형식이어야 합니다.
- OOD 모델의 계산 연령 범위는 2–100세입니다. 필수값이 없거나 범위를 벗어나면 `Not calculated`로 표시됩니다.
- `Pat_ID`는 앞자리 0이 사라지지 않도록 텍스트로 저장됩니다.
- 변환할 CSV나 저장할 XLSX 파일이 Excel에서 열려 있으면 저장 오류가 날 수 있습니다.
- 오류가 나면 사용자 폴더의 `IOLMasterParser_error.txt`를 개발자에게 보내 주세요.

## 개발자/관리자 빌드 방법

Windows PC에서만 EXE 빌드를 권장합니다.

1. Python 3.9 이상을 설치합니다.
   - python.org에서 설치합니다.
   - 설치 시 `Add python.exe to PATH` 또는 py launcher 사용 가능 옵션을 켭니다.
2. 이 폴더에서 `build_windows.bat`를 더블클릭합니다.
3. 빌드가 끝나면 아래 파일이 생성됩니다.

```text
dist\IOLMasterParser.exe
```

## OOD 모델 재학습

원본 자료를 변경한 경우 다음 명령으로 모델과 검증 요약을 다시 생성합니다. 학습 스크립트는 Python 표준 라이브러리만 사용합니다.

```text
py -3 modeling\train_ood_model.py IOLMaster700_corrected_3.xlsx
```

연령층별 Core/Extended bundle은 다음 명령으로 생성합니다.

```text
py -3 modeling\train_age_stratified_ood_models.py IOLMaster700_corrected_3.xlsx
```

생성 파일:

```text
models\biometry_ood_core_v1.json
reports\biometry_ood_core_v1_validation.json
models\biometry_ood_age_stratified_v2.json
reports\biometry_ood_age_stratified_v2_validation.json
```

모델 내용을 변경하는 재학습에서는 버전을 명시합니다.

```text
py -3 modeling\train_ood_model.py IOLMaster700_corrected_3.xlsx --version core-v1.1.0
```

모델 파일에는 환자별 기록이나 식별정보가 포함되지 않습니다. 원본 파일의 SHA-256, 집계 계수, age-adjustment 계수, robust covariance/precision matrix와 익명화된 reference-distance 분포만 저장됩니다.

## 연구용 웹 계산기

프로젝트 폴더에서 정적 서버를 실행한 뒤 웹 계산기를 엽니다.

```text
py -3 -m http.server 8765 --bind 127.0.0.1
http://127.0.0.1:8765/web/
```

웹 버전은 Age, AL, Mean K, ACD, LT를 서버에 전송하지 않고 브라우저 안에서 계산합니다. 환자 이름, 등록번호, 생년월일 및 검사일 입력란은 없습니다. 실제 외부 배포 시에도 접속 로그나 분석 도구가 입력값을 수집하지 않도록 유지해야 합니다.

전공의에게는 `dist\IOLMasterParser.exe` 하나만 전달하면 됩니다.

## 배포 팁

- 병원 PC 보안 때문에 처음 실행 시 Windows SmartScreen 경고가 뜰 수 있습니다.
- 가능하면 병원 내부 공유폴더, 인트라넷, 공식 이메일로 배포하세요.
- 배포 전 샘플 CSV 1개로 정상 변환 여부와 `Pat_ID` 앞자리 0 보존 여부를 꼭 확인하세요.
