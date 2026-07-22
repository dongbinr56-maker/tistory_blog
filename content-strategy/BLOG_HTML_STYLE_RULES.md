# 블로그 HTML 공통 스타일 규칙

이 문서는 주제나 카테고리와 관계없이 모든 블로그 원고와 작성 자동화에 적용한다.

## 데이터 표 헤더 정렬

- HTML에 데이터 표(`<table>`)가 들어가면 모든 헤더 셀(`<th>`)을 가운데 정렬한다.
- 각 `<th>`의 인라인 `style`에 `text-align:center;`를 직접 넣는다. `<thead>` 안의 열 헤더뿐 아니라 본문에 사용한 행 헤더도 같은 규칙을 적용한다.
- 본문 셀(`<td>`)의 정렬은 데이터 성격에 맞게 정할 수 있지만, `<th>` 중앙 정렬에는 예외를 두지 않는다.
- 외부 CSS나 테마 상속에만 의존하지 않는다. 티스토리 HTML과 이메일 미리보기에서 같은 결과가 나와야 한다.

```html
<th style="padding:10px; text-align:center;">항목</th>
```

납품 전 HTML의 모든 `<th>` 여는 태그를 확인해 인라인 `style`에 `text-align:center`가 있는지 검수한다.

## 이미지 파일명

최종 납품 이미지는 Asia/Seoul 기준 실행 날짜와 최종 카테고리·제목을 사용해 다음 형식의 PNG 파일로 저장한다.

```text
YYYY-MM-DD_블로그카테고리_대표이미지_블로그제목.png
YYYY-MM-DD_블로그카테고리_본문1_블로그제목.png
YYYY-MM-DD_블로그카테고리_본문2_블로그제목.png
```

- 날짜, 카테고리, 이미지 역할, 제목 사이에는 밑줄(`_`)을 한 개씩 사용한다.
- 이미지 역할은 `대표이미지`, `본문1`, `본문2` 중 하나만 사용한다.
- 카테고리와 제목의 공백은 하이픈(`-`)으로 바꾸고, Windows와 macOS 파일명에서 사용할 수 없는 문자(`< > : " / \ | ? *`), 제어문자, 이름 끝의 마침표·공백은 하이픈으로 바꾼다. 연속된 하이픈은 한 개로 줄인다.
- 전체 파일명이 180자를 넘으면 앞의 날짜·카테고리·역할은 유지하고 제목 부분만 뒤에서 줄인다.
예시:

```text
2026-07-19_AI-업무-자동화_대표이미지_ChatGPT-이력서-점검-채용공고와-어긋난-근거-5개-찾기.png
```

## 로컬 미리보기와 티스토리 붙여넣기용 HTML 분리

최종 납품에서는 용도가 다른 HTML을 같은 파일처럼 취급하지 않는다.

1. `*-local-preview.html`: HTML 파일과 이미지 3장을 같은 폴더에 둘 때 macOS와 Windows에서 확인하는 로컬 미리보기다. 세 `src`에는 `./정확한-파일명.png`를 사용한다.
2. `*-tistory-paste.html`: 티스토리 HTML 편집기에 전체 소스를 붙여넣는 발행용 파일이다. 세 `src`에는 실제로 공개 접근을 확인한 HTTPS 이미지 주소만 사용한다.

- 대표 이미지는 `<article>` 시작부에, 본문 이미지 2장은 원고에서 정한 위치에 실제 `<figure>`와 `<img>`로 넣는다.
- 본문 이미지 주석 `<!-- BODY_IMAGE_1_INSERT_HERE -->`, `<!-- BODY_IMAGE_2_INSERT_HERE -->`는 각 `<figure>` 바로 앞에 한 번씩 유지한다.
- 로컬 미리보기에는 사용자명에 종속되는 `C:\Users\...\Downloads`, `/Users/.../Downloads`, `file://` 절대경로를 사용하지 않는다.
- 티스토리 붙여넣기용 HTML에는 `./`, `file:`, `blob:`, `data:` 이미지 주소를 사용하지 않는다. Base64 인라인 이미지는 파일 크기, 보안 필터, 대표이미지 처리 결과가 불확실하므로 발행 해결책으로 인정하지 않는다.
- 기본 공개 이미지 호스팅은 `config/site.json`의 `draft_assets_base_url`과 연결된 GitHub Pages 자산 경로를 사용한다. 다른 호스트를 쓰면 공개 접근과 장기 유지 권한을 먼저 확인한다.
- 발송 전 세 HTTPS 이미지 URL을 각각 열어 HTTP 200과 `image/*` Content-Type을 확인한다.

```html
<figure style="margin:24px 0;">
  <img src="./2026-07-19_AI-업무-자동화_본문1_예시-제목.png" alt="본문 흐름을 설명하는 이미지" style="display:block; width:100%; height:auto;" />
</figure>
```

`./` 상대경로는 로컬 미리보기에서만 동작한다. 티스토리 HTML 편집기는 Downloads 폴더를 읽거나 로컬 PNG를 업로드하지 않는다. 따라서 이메일의 “복사 가능한 HTML”에는 `*-tistory-paste.html`만 넣고, `*-local-preview.html`을 그대로 붙여넣으라고 안내하지 않는다.

발행용 파일은 다음 명령으로 만든다. 이 명령은 이미지 3장을 공개 자산 폴더에 `cover.png`, `body-1.png`, `body-2.png`로 복사하고 발행 HTML의 `src`를 HTTPS 주소로 바꾼다.

```powershell
tistory-newsroom prepare-publish `
  --html "원고-local-preview.html" `
  --asset-dir "docs/tistory/assets/deliveries/YYYY-MM-DD/slug" `
  --asset-base-url "https://GITHUB_ID.github.io/REPOSITORY/tistory/assets/deliveries/YYYY-MM-DD/slug" `
  --output "원고-tistory-paste.html"
```

자산을 공개 호스트에 반영하기 전에는 발행용 파일을 완성됐다고 표시하지 않는다. 반영 후 세 URL의 HTTP 응답과 티스토리 미리보기를 확인해야 납품 완료다. 티스토리 자체 대표이미지/썸네일 등록이 필요하면 대표 PNG는 에디터에서 별도로 업로드한다.
