# IOLMaster 700 Biometry Parser

IOLMaster 700 Export CSV를 eye-based XLSX로 변환하고, age-adjusted biometry OOD score를 계산하는 Windows용 무설치 프로그램입니다.

## 전공의 사용법

1. `IOLMasterParser.exe`를 더블클릭합니다.
2. `CSV 선택`을 누르고 IOLMaster 700 Export CSV 파일을 고릅니다.
3. `변환 시작`을 누릅니다.
4. 저장할 XLSX 파일 이름을 선택합니다.
5. 완료 메시지가 뜨면 생성된 XLSX 파일을 Excel에서 열어 확인합니다.

## Biometry OOD 결과

Core 모델 입력은 `Age`, `AL`, `Mean K`, `ACD`, `LT`이고, Extended 모델은 `WTW`, `CCT`를 추가합니다. `Mean K`는 IOLMaster의 `R1`, `R2`와 keratometric constant 337.5를 이용해 계산합니다. 연령 효과를 보정한 뒤 입력변수 조합의 robust Mahalanobis distance를 계산합니다.

```text
Core: age-standardized AL / Mean K / ACD / LT
Extended: Core + age-standardized WTW / CCT
```

출력 열의 의미는 다음과 같습니다.

```text
OOD_Percentile < 90.0       Typical anatomy
90.0 이상, 97.5 미만       Uncommon anatomy
97.5 이상                  Rare anatomy
```

`OOD_Reference_Context`는 age-weighted calibration 기준에서 이 정도 이상으로 드문 눈의 대략적 빈도를 표시합니다. `OOD_Distance`는 연구 및 재현성을 위한 기술 지표이며, 웹 화면에서는 접힌 세부정보로만 제공합니다. `OOD_Largest_Marginal_Deviations`는 절대 standardized deviation이 큰 두 축을 표시합니다. 이는 Mahalanobis distance의 인과적 분해나 굴절오차 설명이 아닙니다.

현재 활성 모델은 `continuous-age-bilateral-v3.1.0`입니다. 2–100세를 하나의 연속 age-adjustment로 처리하고, eligible OD와 OS를 모두 사용하되 같은 환자의 양안은 항상 동일한 data split에 배정합니다. WTW와 CCT가 모두 유효하면 Extended, 둘 중 하나라도 없으면 Core를 선택합니다. 해부학적 희귀도를 나타낼 뿐, 굴절 prediction error나 최적 formula를 직접 예측하지 않습니다. 외부 검증과 술후 결과 검증 전에는 임상 의사결정 기준으로 사용하지 마십시오.

## OOD 모델 구현 로직

### 1. 기준군 생성

학습 원본은 `IOLMaster700_corrected_3.xlsx`의 `Corrected_All_Eyes` worksheet입니다. 학습 스크립트는 다음 순서로 기준군을 만듭니다.

1. `test`, `demo`, `sample` ID를 제외합니다.
2. DOB와 검사일로 검사 당시 나이를 계산합니다: `(검사일 - DOB) / 365.2425`.
3. 필수 입력이 없거나 사전 정의된 물리적 범위를 벗어난 행을 제외합니다.
4. 동일 환자·동일 안에 반복검사가 있으면 가장 최근 valid 검사를 사용합니다.
5. 동일 환자의 eligible 양안을 모두 포함합니다.
6. 환자 단위 SHA-256 split으로 derivation 55%, tuning 15%, calibration 15%, untouched test 15%를 분리하여 OD와 OS의 split leakage를 방지합니다.
7. Core와 Extended 모델은 별도로 학습·보정·검증합니다.

현재 입력 허용범위는 다음과 같습니다.

```text
AL       14–38 mm
Mean K   30–65 D
ACD      0.8–6.0 mm
LT       2.0–8.0 mm
WTW      8.0–16.0 mm
CCT      0.35–0.80 mm
```

V3.1은 Core 8,177안/4,501명과 Extended 8,164안/4,498명을 사용합니다. Core의 derivation은 4,518안/2,490명, tuning 1,133안/628명, calibration 1,246안/681명, test 1,280안/702명입니다. Extended는 각각 4,511안/2,487명, 1,133안/628명, 1,245안/681명, 1,275안/702명입니다.

### 2. Mean K와 연령 보정

각막곡률반경이 mm 단위일 때 Mean K는 다음과 같이 계산합니다.

```text
Mean K = ((337.5 / R1) + (337.5 / R2)) / 2
```

모든 입력변수의 연령별 기대값은 Huber piecewise-linear spline으로 적합합니다. Huber tuning constant는 1.345이고 최대 100회 iterative reweighted least squares를 수행합니다. 연령 knot는 5, 10, 15, 18, 30, 40, 55, 70, 85세입니다.

```text
t = (Age - 50) / 10
Expected(feature | Age) = beta0 + beta1*t + Σ beta(k)*max(0, t-knot(k))
Age-adjusted feature = observed feature - Expected(feature | Age)
```

평균만 보정하면 연령별 residual dispersion 차이가 남을 수 있으므로 각 feature에서 250명의 nearest-age derivation 환자로 `1.4826 × MAD` scale을 구하고 age anchor 사이를 선형 보간합니다.

```text
Age-standardized residual = Age-adjusted feature / local MAD scale(Age)
```

따라서 화면의 `Age-adjusted ACD/LT`는 실제 해부학적 길이가 아니라 연령 기대값을 뺀 residual입니다.

### 3. Robust Mahalanobis distance

Core는 4차원, Extended는 6차원 feature vector를 사용합니다.

```text
Core      = age-standardized [AL, Mean K, ACD, LT]
Extended  = age-standardized [AL, Mean K, ACD, LT, WTW, CCT]
```

기준군의 중심과 공분산은 derivation set에서 scikit-learn의 reweighted Minimum Covariance Determinant로 추정합니다. `support_fraction=0.75`, `random_state=20260710`을 사용하고 최대 eigenvalue의 `1e-8`을 eigenvalue floor로 적용합니다. 추정한 robust location `mu`와 covariance `Sigma`로 거리를 계산합니다.

```text
OOD distance = sqrt((x - mu)^T * inverse(Sigma) * (x - mu))
```

이 거리는 한 변수의 극단값뿐 아니라, 개별 변수는 정상범위여도 서로 드문 조합인 경우 증가할 수 있습니다.

### 4. Percentile과 임상 표시

결과 percentile은 chi-square 분포를 가정한 이론적 확률이 아닙니다. 모델 학습에 사용하지 않은 patient-level split의 bilateral calibration eyes로 age-weighted empirical distance distribution을 만듭니다. 각 눈을 추정 단위로 사용하되 effective N과 test confidence interval은 patient cluster를 고려합니다.

```text
weight(i) = exp(-0.5 × ((calibration age(i) - patient age) / bandwidth)^2)
OOD percentile = 100 × Σ weight(distance(i) < patient distance) / (1 + Σ weight)
```

Gaussian age bandwidth는 별도 tuning set에서 사전 후보 4, 6, 8, 10, 12년을 비교해 선택했습니다. Core는 8년, Extended는 4년입니다. 분모의 `+1`은 상위 꼬리확률이 0이 되는 것을 막습니다. Core와 Extended는 각각의 기준분포로 따로 보정되므로 두 tier의 percentile을 직접 합치면 안 됩니다. 앱은 Extended 사용 시 Core-only sensitivity 결과를 기술정보에 함께 표시합니다.

표시 기준은 다음과 같습니다.

```text
< 90.0 percentile          Typical anatomy
90.0–<97.5 percentile      Uncommon anatomy
>= 97.5 percentile         Rare anatomy
```

90과 97.5 percentile은 outcome에서 도출한 cutoff가 아니라 prespecified descriptive category입니다. `약 N안 중 1안`은 add-one smoothing을 포함한 age-weighted 상위 꼬리비율의 역수입니다. `OOD_Largest_Marginal_Deviations`는 robust 중심에서 변수별 standardized deviation이 큰 두 항목을 보여주는 설명용 지표입니다. 변수 간 상관관계가 포함된 Mahalanobis distance의 정확한 기여도나 prediction error의 원인을 뜻하지 않습니다.

### 5. 실행 시 모델 선택

2–100세에서 동일한 continuous age-adjusted 모델을 사용합니다. WTW와 CCT가 모두 숫자이고 허용범위 안이면 Extended를 사용하고, 하나라도 없거나 범위를 벗어나면 Core를 사용합니다. Core 필수 입력이 없거나 범위를 벗어나면 `Not calculated`를 반환합니다.

### 6. 현재 모델의 해석 한계

- 단일기관 후향적 기준분포이며 외부기관·다른 biometer에서 보정되지 않았습니다.
- 임상 적응증, phakic status, prior refractive surgery와 device quality warning을 원본만으로 확인할 수 없습니다.
- age adjustment는 본원 자료의 cross-sectional age trend를 제거하며 longitudinal biological change를 의미하지 않습니다.
- tuning, calibration, test는 학습에서 분리했지만 아직 외부기관 calibration은 없습니다.
- 양안 상관은 patient-level split과 cluster-bootstrap test CI로 처리하지만, covariance geometry 자체의 추정 단위는 eye입니다.
- 18–39세 untouched test는 Core 52안/27명, Extended 50안/27명으로 작아 해당 연령의 calibration 정밀도가 제한적입니다.
- 특히 18–39세 Extended는 age-local effective N이 작아 add-one smoothing 후 가능한 percentile 상한이 97.5 미만일 수 있으며, 이 연령에서는 극단적 입력도 `Rare`가 아니라 `Uncommon`으로 표시될 수 있습니다.
- 높은 percentile은 `드문 해부학적 조합`을 뜻하며, 측정오류나 질환을 확진하지 않습니다.
- 술후 prediction error, formula disagreement 또는 특정 formula의 우월성을 직접 예측하지 않습니다.
- 임상적 유용성 주장을 위해서는 EMR 확인, 외부검증과 술후 굴절결과 기반 outcome validation이 필요합니다.

### 7. V3.1 내부 기술검증

학습과 tuning에 사용하지 않은 patient-level split의 bilateral test에서 다음 결과를 얻었습니다.

```text
Core      1,280 eyes / 702 patients: Typical 90.5% / Uncommon 7.3% / Rare 2.3% / KS 0.032
Extended  1,275 eyes / 702 patients: Typical 92.1% / Uncommon 6.1% / Rare 1.8% / KS 0.022
```

Patient-cluster bootstrap 95% CI는 Core Rare 1.3–3.4%, Extended Rare 1.0–2.8%였습니다. Core와 Extended의 test category 일치도는 94.1%, Rare 분류 변경률은 0.8%였습니다. One-eye V3와 bilateral V3.1의 category 일치도는 Core 98.3%, Extended 98.0%였습니다. 이는 calibration과 연속성에 대한 내부 기술검증이며 임상 outcome validation이 아닙니다. 전체 수치는 `reports/biometry_ood_bilateral_v31_validation.json`에 저장됩니다.

## Pilot postoperative workbook 공식 해석 규칙

아래 규칙은 다음 두 수기 수집 workbook에만 적용합니다. 일반적인 IOLMaster 700 Export CSV 또는 다른 연구자료에 자동으로 적용하면 안 됩니다.

```text
Pilot_150_extreme_biometry_signal_discovery_postop_collection_사우진.xlsx
Pilot_40_second_wave_discordant_TK_astig_postop_collection_이동수.xlsx
```

연구자가 확인한 데이터 입력 convention은 다음과 같습니다.

1. `Pred_SE_Haigis_D` 또는 `PE_Haigis_D`에 값이 있지만 `Hoffer Q`와 `SRK/T` 열이 모두 비어 있는 행은 post-refractive case입니다.
2. 이 post-refractive case에서 `Haigis` 열에 기록된 값은 standard Haigis가 아니라 **Haigis-L**입니다. 별도 Haigis-L 열이 없어 Haigis 열을 대신 사용했습니다.
3. Haigis-L을 사용한 모든 case는 `Barrett_TK` 열에 **Barrett True-K TK** 결과를 기록했습니다.
4. 따라서 표·그림·통계에서는 해당 행의 `Haigis`를 `Haigis-L`, `Barrett_TK`를 `Barrett True-K TK`로 다시 표기합니다.
5. Hoffer Q와 SRK/T 값이 있는 routine case의 `Haigis` 열은 standard Haigis로 해석합니다.
6. Routine case와 post-refractive case는 공식 구성과 적응증이 다르므로 formula spread, MAE, median absolute PE 및 공식 순위를 합쳐 계산하지 않습니다.

현재 pilot 분석에서 사용하는 식은 다음과 같습니다.

```text
MR_SE = MR_Sphere + MR_Cylinder / 2
Prediction error (PE) = Predicted_SE - Postoperative_MR_SE
Formula spread = max(available Predicted_SE) - min(available Predicted_SE)
```

따라서 positive PE는 실제 술후 MRSE가 예측보다 더 myopic했다는 뜻이고, negative PE는 실제 결과가 예측보다 더 hyperopic했다는 뜻입니다. Formula spread는 공식 간 불일치의 크기이며, 어느 공식이 정확한지 또는 모든 공식이 공유하는 입력오류가 있는지를 단독으로 판단하지 않습니다.

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

V3 학습용 패키지를 설치한 뒤 모델과 검증 요약을 생성합니다. 배포 앱과 웹 계산기는 이 패키지들을 필요로 하지 않습니다.

```text
py -3 -m pip install -r requirements-modeling.txt
py -3 modeling\train_bilateral_ood_v31.py IOLMaster700_corrected_3.xlsx
```

생성 파일:

```text
models\biometry_ood_bilateral_v31.json
reports\biometry_ood_bilateral_v31_validation.json
```

V1/V2와 one-eye V3 학습 스크립트 및 artifact는 방법 비교와 재현을 위해 보존합니다. V3.1 모델 파일에는 환자 식별정보나 연결 가능한 row-level biometry가 포함되지 않습니다. 원본 SHA-256, 집계 계수, 연령 보정계수, robust covariance/precision matrix, calibration age-distance와 익명 cluster 번호, 변수별 비식별 분포만 저장됩니다.

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
