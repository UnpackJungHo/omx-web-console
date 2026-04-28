# DESIGN.md - OMX-F Robot Console Color Guide

이 문서는 미래 지향적인 하이테크 감성을 담은 **'Electric Blue'** 테마의 시각적 규격과 UI 스타일 가이드를 정의합니다. 어두운 배경과 선명한 블루 액센트의 대비를 통해 산업용 로봇 제어의 정밀함과 현대적인 감각을 동시에 전달합니다.

---

## 1. Core Color Palette

| Category | Color Name | Hex Code | Application |
| :--- | :--- | :--- | :--- |
| **Background** | Deep Midnight | `#0A0E14` | 어플리케이션 전체의 메인 배경색 |
| **Surface** | Slate Navy | `#1E293B` | 컨트롤 카드, 로그 창, 패널의 배경 |
| **Primary** | Electric Cyan | `#00F2FF` | 핵심 강조색, 활성 슬라이더, 상태 지표 |
| **Secondary** | Cyber Blue | `#3B82F6` | 보조 버튼, 일반 인터랙션 요소 |
| **Divider** | Grid Slate | `#334155` | 섹션 구분선, 3D 뷰포트 그리드 |
| **Alert** | Emergency Red | `#EF4444` | 정지(Stop) 버튼 및 오류 상태 |

---

## 2. Typography & Text Colors

- **Font Family**:
  - 기본: `Inter` 또는 `Pretendard` (가독성 중심)
  - 수치/로그: `JetBrains Mono` 또는 `Roboto Mono` (공학적 정밀도 강조)

| Usage | Color Hex | Description |
| :--- | :--- | :--- |
| **Heading / Value** | `#F8FAFC` | 가장 밝은 텍스트 (조인트 각도, 타이틀) |
| **Body / Label** | `#CBD5E1` | 일반 레이블 및 설명 텍스트 |
| **Muted / Unit** | `#94A3B8` | 단위(deg), 비활성 로그, 보조 정보 |

---

## 3. UI Component Styles

### 🟦 Sliders (Control Panel)
- **Track**: `#1E293B` 배경에 1px 테두리 적용.
- **Fill (Progress)**: `Electric Cyan` 적용, 끝부분에 미세한 글로우 효과.
- **Handle**: 하얀색 원형 노브, 마우스 오버 시 `Electric Cyan` 후광 효과.

### 🔳 Cards & Panels
- **Border**: `#334155` 색상의 1px 선을 사용하여 섹션 구분.
- **Border Radius**: `4px` (각진 느낌을 주어 기계적이고 정밀한 인상 부여).
- **Shadow**: `0 4px 20px rgba(0, 0, 0, 0.5)` (깊이감 형성).

### 🔘 Buttons
- **Action (Execute)**: `Electric Cyan` 보더와 텍스트, 배경은 투명하거나 아주 어두운 블루.
- **Emergency (Stop)**: `Emergency Red` 배경에 하얀색 텍스트.
- **Hover State**: 배경색의 명도를 10% 높이고 글로우(Glow) 효과 추가.

---

## 4. Visual Effects (FX)

- **Neon Glow**: 활성화된 상태나 중요한 지표 주변에 `box-shadow: 0 0 12px rgba(0, 242, 255, 0.4);` 적용.
- **3D Viewport**: 배경은 `#05070A`로 메인 배경보다 더 어둡게 설정하여 로봇 팔 모델에 시선이 집중되도록 함.
