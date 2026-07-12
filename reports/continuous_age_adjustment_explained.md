# Continuous age adjustment 설명 — “전체 연령에서 robust spline”이란?

> 대상 모델: `continuous-age-bilateral-v3.2.0` (Overall age adjustment는 V3.1과 동일)
> 목적: 2–100세를 소아·젊은 성인·성인 모델로 딱 잘라 나누지 않고, 검사 나이에 맞는 연속적인 기준을 만드는 것

## 한 문장 설명

**Robust spline은 나이에 따른 정상적인 변화는 따라가되, 몇 개의 극단값에는 덜 흔들리도록 만든 “구부러질 수 있는 연령 기준선”입니다.**

여기서 “전체 연령에서 적합한다”는 말은 모든 나이를 같은 평균과 비교한다는 뜻이 아닙니다.

> 2–100세 derivation 자료를 함께 사용해 하나의 연속적인 연령 곡선을 만들고, 각 환자는 그 곡선에서 자기 나이에 해당하는 지점과 비교합니다.

## 왜 연령군을 없앴나?

과거 V2에서는 다음처럼 세 모델을 따로 만들었습니다.

```text
2–17세    Pediatric model
18–39세   Young-adult model
40–100세  Adult model
```

이 방식은 이해하기 쉽지만 경계 문제가 있습니다.

- 17.9세와 18.0세가 서로 다른 모델을 사용합니다.
- 39.9세와 40.0세도 서로 다른 중심·공분산·percentile 기준을 사용합니다.
- 경계 바로 전후인데도 OOD 점수가 갑자기 달라질 수 있습니다.
- 표본이 작은 연령군은 모델 전체가 불안정해질 수 있습니다.

현재 V3.2에서는 2–100세가 같은 모델을 사용하되, 평균·변동폭·percentile 기준이 나이에 따라 연속적으로 변합니다.

## Spline이란?

나이와 생체계측값의 관계가 완전한 직선이라고 가정하면 다음과 같습니다.

```text
Expected ACD = a + b × Age
```

하지만 실제 연령 변화는 소아기, 젊은 성인기, 백내장 연령대에서 기울기가 다를 수 있습니다. Spline은 하나의 직선을 강요하지 않고, 몇 개 지점에서 기울기가 바뀔 수 있게 합니다.

현재 knot는 다음과 같습니다.

```text
5, 10, 15, 18, 30, 40, 55, 70, 85세
```

이를 “구부러지는 자”로 생각하면 쉽습니다.

```text
하나의 딱딱한 직선
────────────────────────

Spline
──────╱────────╲─────────╱────
      18세      55세      85세
```

중요한 점은 knot가 연령군 경계가 아니라는 것입니다.

- Knot에서 곡선이 끊어지지 않습니다.
- 기대값은 앞뒤로 연속적입니다.
- 다만 나이에 따른 변화의 기울기가 달라질 수 있습니다.

따라서 17.9세와 18.0세는 거의 같은 기대값을 갖습니다.

## Robust란?

일반 회귀는 아주 특이한 눈 몇 개가 연령 곡선을 크게 끌어당길 수 있습니다. 그러나 OOD 모델을 만드는 자료에는 실제 특이안, 측정오류 가능 사례 또는 특별한 임상 상태가 일부 섞여 있을 수 있습니다.

현재 모델은 Huber regression을 사용합니다.

```text
곡선에 가까운 관측값   → 보통 가중치
곡선에서 매우 먼 관측값 → 낮은 가중치
```

극단값을 무조건 삭제하는 것은 아닙니다. 곡선에서 멀수록 평균 연령 추세를 결정하는 영향만 줄입니다.

따라서 `robust spline`은 다음 두 단어의 결합입니다.

```text
Spline = 연령에 따라 기울기가 달라질 수 있는 연속 곡선
Robust = 극단값 몇 개에 곡선이 과도하게 끌려가지 않게 함
```

## 실제 수식

먼저 나이를 중심화·스케일링합니다.

```text
t = (Age − 50) / 10
```

각 feature의 연령 기대값은 다음 형태입니다.

```text
Expected(feature | Age)
  = β0 + β1·t
    + Σ βk·max(0, t − scaled_knotk)
```

`max(0, t − knot)` 항은 해당 knot 이전에는 0이고, knot 이후에는 새로운 기울기를 추가합니다. 여러 항이 연결되어 하나의 연속적인 piecewise-linear curve가 됩니다.

각 feature마다 별도의 곡선을 학습합니다.

- AL
- Mean K
- ACD
- LT
- Extended 모델에서는 WTW, CCT 추가

구현: [`train_continuous_ood_v3.py`](../modeling/train_continuous_ood_v3.py)

## 실제 환자에게 적용하는 세 단계

Continuous age adjustment는 spline 하나로 끝나지 않습니다. 세 층으로 구성됩니다.

### 1. 같은 나이의 기대값을 뺀다

```text
Age residual
  = Observed feature − Expected(feature | patient age)
```

예를 들어 `Age-adjusted ACD = −0.3 mm`는 ACD가 음수라는 뜻이 아닙니다.

> 본원 derivation 자료에서 같은 나이에 기대되는 ACD보다 0.3 mm 얕다는 뜻입니다.

### 2. 같은 나이의 변동폭으로 나눈다

평균만 빼도 충분하지 않습니다. 나이에 따라 사람들 사이의 변동폭이 다를 수 있기 때문입니다.

모델은 여러 age anchor에서 나이가 가장 가까운 derivation eye record 250개의 잔차를 사용해 robust scale을 계산합니다.

```text
Local scale(Age) = 1.4826 × MAD
```

Age anchor:

```text
2, 5, 8, 11, 14, 17, 20, 25, 30, 35,
40, 50, 60, 70, 80, 90, 100세
```

Anchor 사이의 scale은 선형 보간합니다.

```text
Age-standardized residual
  = Age residual / Local MAD scale(Age)
```

따라서 같은 0.3 mm 차이라도 그 나이에서 흔한 차이면 작은 z가 되고, 매우 드문 차이면 큰 z가 됩니다.

#### 이 age anchor는 왜 이렇게 선택했나?

결론부터 말하면, **현재 저장소에는 이 anchor 목록을 데이터에서 최적화했다는 근거나 별도 tuning 기록이 없습니다.** 최초 continuous V3 코드에 미리 지정된 수동 설계값입니다.

간격에는 다음 패턴이 있습니다.

```text
2–20세    약 3년 간격
20–40세   약 5년 간격
40–100세  약 10년 간격
```

이 배치에서 추정할 수 있는 설계 의도는 다음과 같습니다.

- 성장기에는 평균과 변동폭이 빠르게 달라질 수 있으므로 촘촘하게 둡니다.
- 성인기에는 변화가 상대적으로 완만하다고 보고 성기게 둡니다.
- 2세와 100세를 포함해 모델 범위의 양 끝을 덮습니다.
- Anchor 사이를 선형 보간해 scale이 갑자기 바뀌지 않게 합니다.

하지만 이는 **합리적인 engineering heuristic**이지, 현재 자료에서 최적이라고 입증된 선택은 아닙니다.

또한 `age knot`와 `scale anchor`는 역할이 다릅니다.

| 구분 | 역할 |
|---|---|
| Spline knot | 연령별 **평균 기대값 곡선의 기울기**가 바뀔 수 있는 위치 |
| Scale anchor | 연령별 **잔차 변동폭(MAD)**을 계산해 저장하는 위치 |

Scale anchor는 새로운 연령군을 만드는 경계가 아닙니다. 각 anchor에서 nearest 250안을 다시 선택하며, 이웃 anchor끼리는 많은 눈을 공유할 수 있습니다.

#### 실제로 250안은 얼마나 가까운가?

현재 V3.2 Core derivation 4,518안에서 각 anchor의 nearest 250안 연령 범위를 확인하면 다음과 같습니다.

| Anchor | Nearest 250안의 실제 연령 범위 | 중앙값 |
|---:|---:|---:|
| 2세 | 2.8–8.0세 | 5.8세 |
| 5세 | 2.8–8.0세 | 5.8세 |
| 10세에 가까운 11세 anchor | 7.9–13.9세 | 9.7세 |
| 20세 | 9.7–30.1세 | 12.6세 |
| 25세 | 11.0–39.2세 | 22.8세 |
| 40세 | 31.5–48.7세 | 42.9세 |
| 50세 | 46.1–54.0세 | 50.7세 |
| 70세 | 69.2–70.8세 | 70.0세 |
| 90세 | 83.8–95.5세 | 86.4세 |
| 100세 | 83.8–98.6세 | 86.6세 |

이 표는 중요한 한계를 보여줍니다.

- 2세와 5세 anchor는 사실상 같은 250안을 사용합니다.
- 18–39세 자료가 적어 20세와 25세 anchor의 창이 매우 넓고 비대칭입니다.
- 90세와 100세 anchor도 대부분 80대 자료에 의해 결정됩니다.
- 따라서 “100세 local scale”을 100세 부근의 충분한 자료로 추정했다고 해석하면 안 됩니다.

Nearest-neighbor 방식은 자료가 많은 60–80대에서는 매우 국소적이고, 자료가 적은 연령에서는 자동으로 넓어집니다. 표본이 적어도 계산은 가능하게 해주지만, 희소 연령의 scale이 실제 그 나이를 정확히 대표한다는 보장은 약합니다.

#### 더 방어적인 선택 방법

향후에는 anchor 목록 하나를 정답으로 간주하기보다 다음 민감도 분석이 필요합니다.

1. Nearest-neighbor 수를 150, 250, 400으로 바꿔 category 안정성을 비교합니다.
2. 현재 grid와 5년 고정 grid, 연령 분위수 기반 anchor를 비교합니다.
3. Untouched test에서 연령대별 percentile KS와 Typical/Uncommon/Rare 비율을 비교합니다.
4. 같은 눈의 percentile과 category가 anchor 설계에 따라 얼마나 바뀌는지 확인합니다.
5. 가능하면 local MAD 자체도 bandwidth를 tuning set에서 선택하는 연속 smoother로 대체합니다.

현재 anchor는 출발점으로는 이해 가능한 선택이지만, 특히 18–39세와 90세 이상에서는 외부검증과 sensitivity analysis 없이 강하게 정당화하기 어렵습니다.

### 3. OOD percentile도 가까운 나이와 비교한다

Mahalanobis distance가 계산된 뒤 percentile을 만들 때도 모든 연령의 calibration eye를 똑같이 사용하지 않습니다.

```text
weight(i)
  = exp{−0.5 × [(calibration age(i) − patient age) / bandwidth]²}
```

환자와 나이가 가까운 calibration eye는 큰 가중치를 받고, 먼 연령은 작은 가중치를 받습니다.

현재 V3.2 Overall OOD의 bandwidth:

```text
Core       8년
Extended   4년
```

Bandwidth는 4, 6, 8, 10, 12년 후보 중 별도 tuning set에서 연령별 percentile calibration이 가장 나은 값을 선택했습니다.

## 전체 계산 흐름

```text
원래 측정값
    ↓
Robust spline에서 해당 나이의 기대값 계산
    ↓
Observed − Expected(Age)
    ↓
해당 나이의 local MAD로 나눔
    ↓
연령표준화 AL·K·ACD·LT(±WTW·CCT)
    ↓
Robust Mahalanobis distance
    ↓
가까운 연령의 calibration eyes로 age-local percentile 계산
```

## 과거와 현재를 쉽게 비교하면

| 질문 | 과거 age-stratified V2 | 현재 continuous V3.1 |
|---|---|---|
| 누구와 비교하는가? | 같은 연령군 전체 | 자기 나이에 가까운 눈 |
| 연령 기준 | 2–17 / 18–39 / 40–100 | 2–100세 연속 곡선 |
| 평균 보정 | 군별 quadratic regression | 전체 연령 robust spline |
| 분산 보정 | 군 안에서 사실상 공통 | 연령별 local MAD |
| Percentile | 군별 거리분포 | age-weighted 거리분포 |
| 18·40세 경계 | 모델 교체 가능 | 연속적으로 변화 |

## 코드에 age band가 아직 남아 있는 이유

현재 코드에도 다음 구간이 남아 있습니다.

```text
2–17, 18–39, 40–59, 60–79, 80–100
```

이 구간은 환자의 모델을 선택하기 위한 것이 아닙니다. 다음 목적으로 사용합니다.

- 연령별 test 결과 확인
- 특정 연령에서 calibration이 나쁜지 확인
- bandwidth 후보 평가
- 연령별 표본 수 보고

실제 점수 계산은 2–100세에서 같은 continuous model을 사용합니다.

## 해석할 때 주의할 점

1. **종단 변화가 아닙니다.** 같은 사람을 수십 년 추적한 결과가 아니라 본원 자료의 cross-sectional age trend입니다.
2. **건강한 정상인 곡선이 아닙니다.** 단일기관 IOLMaster 검사 집단의 robust 기준선입니다.
3. **표본이 적은 연령은 불확실합니다.** 특히 18–39세 Extended calibration의 정밀도가 제한적입니다.
4. **Spline이 질환을 교정하는 것은 아닙니다.** 나이와 함께 변하는 본원 평균 추세를 제거할 뿐입니다.
5. **Knot는 임상 cutoff가 아닙니다.** 곡선이 유연하게 구부러질 수 있도록 정한 계산 지점입니다.

## 최종 요약

> 과거에는 환자를 연령별 방으로 나눈 뒤 그 방의 사람들과 비교했습니다. 현재는 2–100세 전체 자료로 이상치에 덜 흔들리는 하나의 연속적인 연령 기준선을 만들고, 각 환자를 자기 나이에 해당하는 기준점과 비교합니다. 평균뿐 아니라 나이별 변동폭과 percentile 기준까지 연속적으로 보정합니다.

## 관련 파일

- 현재 학습 로직: [`../modeling/train_continuous_ood_v3.py`](../modeling/train_continuous_ood_v3.py)
- 현재 bilateral 모델 학습: [`../modeling/train_bilateral_ood_v32.py`](../modeling/train_bilateral_ood_v32.py)
- 과거 연령군 모델: [`../modeling/train_age_stratified_ood_models.py`](../modeling/train_age_stratified_ood_models.py)
- 현재 검증 결과: [`biometry_ood_bilateral_v32_validation.json`](biometry_ood_bilateral_v32_validation.json)
