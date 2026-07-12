# Age+AL-conditioned geometry score 구현 및 내부 검증

## 한 줄 요약

기존 `Overall OOD`는 그대로 유지하고, **같은 나이와 비슷한 AL을 가진 눈에서 K·ACD·LT(Extended는 WTW·CCT 포함)의 조합이 얼마나 이례적인지** 보여주는 보조 점수를 V3.2에 추가했다. 이 점수에서 AL 자체의 길고 짧음은 이상도로 다시 계산하지 않는다.

## 두 점수의 차이

- `Overall OOD`: 나이 보정 후 AL을 포함한 전체 biometry 조합의 희귀도
- `Geometry given age + AL`: 해당 나이와 AL을 전제로 했을 때 나머지 구조 조합의 불일치 정도

예를 들어 장안이라는 이유만으로 조건부 점수가 높아지지는 않는다. 대신 그 장안에서 기대되는 ACD·LT·K 관계와 실제 측정 조합이 맞지 않을 때 점수가 높아진다. 따라서 두 점수는 경쟁 관계가 아니라 질문이 다르다.

## 계산 방법

1. 기존 robust spline으로 각 측정치를 연령에 대해 연속 보정하고, 연령별 MAD scale로 표준화한다.
2. V3.1에서 확정된 robust location과 covariance는 변경하지 않는다.
3. 표준화된 AL을 조건으로 두고 covariance를 분할한다.
4. `E[나머지 측정치 | AL]`을 뺀 조건부 잔차를 만든다.
5. Schur complement로 얻은 조건부 covariance를 이용해 Mahalanobis distance를 계산한다.
6. 별도 calibration set에서 나이와 AL이 가까운 눈에 더 큰 가중치를 주어 empirical percentile로 변환한다.

조건부 평균과 covariance는 다음과 같다.

```text
E[Y | AL] = μY + ΣYA / ΣAA × (AL - μA)
Cov[Y | AL] = ΣYY - ΣYA ΣAY / ΣAA
```

여기서 `Y`는 Core의 경우 K·ACD·LT, Extended의 경우 K·ACD·LT·WTW·CCT다. AL은 조건을 정하는 데만 쓰며 조건부 거리의 변수에서는 제외한다.

## 보정 bandwidth 선택

Tuning set에서 다음 후보를 비교했다.

- 나이 bandwidth: 4, 6, 8, 10, 12년
- AL bandwidth: 연령 보정·표준화 AL의 0.5, 0.75, 1.0, 1.5, 2.0 SD

전체 uniformity, 연령대별 uniformity, AL 구간별 uniformity, local effective N을 함께 평가한 결과 Core와 Extended 모두 `8년 + AL 1.0 SD`가 선택됐다.

## Untouched test 결과

| Model | Eyes / patients | Median percentile | KS from uniform | Typical | Uncommon | Rare | Effective N p10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Core | 1,280 / 702 | 47.45 | 0.043 | 89.45% | 9.22% | 1.33% | 59.1 |
| Extended | 1,275 / 702 | 47.75 | 0.032 | 88.78% | 9.73% | 1.49% | 59.7 |

환자 단위 cluster bootstrap 95% CI에서 Rare 비율은 Core 0.7–2.1%, Extended 0.8–2.3%였다. 전체 test calibration은 양호하다. 다만 표본이 적은 극단 AL 구간에서는 편차가 더 크다.

| AL 구간 | Core n / KS | Extended n / KS |
|---|---:|---:|
| <22 mm | 59 / 0.212 | 59 / 0.204 |
| 22–24.5 mm | 840 / 0.057 | 838 / 0.025 |
| 24.5–26 mm | 266 / 0.037 | 266 / 0.076 |
| ≥26 mm | 115 / 0.148 | 112 / 0.105 |

따라서 AL 극단에서는 percentile을 정밀한 확률로 읽지 말고, 화면의 effective N 및 calibration ceiling 경고와 함께 해석해야 한다.

## 구현 결과

- 활성 번들: `continuous-age-bilateral-v3.2.0`
- 모델: `models/biometry_ood_bilateral_v32.json`
- 전체 수치 보고서: `reports/biometry_ood_bilateral_v32_validation.json`
- Python/Excel 출력과 브라우저 계산기에 동일한 조건부 수식을 구현했다.
- Extended 사용 시 Core 조건부 점수도 sensitivity 값으로 함께 계산한다.
- V3.1의 Overall score 입력(나이 보정, robust covariance, calibration 자료와 bandwidth)을 byte-level JSON 값으로 그대로 유지하며 회귀 테스트로 고정했다.

## 해석 시 주의

이 점수는 “이 AL에서 구조 조합이 낯선가?”를 설명하는 연구용 기술 지표다. 질환 진단, 측정 오류 판정, IOL formula 선택, 술후 PE 예측을 직접 의미하지 않는다. 현재 조건부 평균은 선형 covariance 관계를 이용하므로 비선형 AL 관계, 외부 기관, 다른 biometer, 극단 AL에서는 별도 검증이 필요하다.
