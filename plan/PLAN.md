# guin-site — plan

목표: 소유자가 평소에 생각하는 것을 마구잡이로 올리는 개인 사이트. 글(가끔 이미지)을 파일로 쓰고, Astro로 만든
생성기가 정적 HTML을 `docs/`에 만든다(도구와 패키지는 필요한 대로 쓴다, `source:as-01`). GitHub Pages가 `docs/`를 서비스한다. 기획의 근거는 `mangsang/`의 원문과
개념이다: 아래 각 절은 개념 하나 이상의 투영이며, 첫 줄에 그 개념을 적는다.

용어: **글 파일**은 `content/posts/<id>.md`이고, 글의 `<id>`는 작성 시각 `YYYYMMDD-HHMMSS`(UTC)다(Q-post). **기록 표**는 글에
붙는 기록을 종류마다 모은 파일이다: `content/links.jsonl`(Q-link), `content/patches.jsonl`(Q-patch), `content/shares.jsonl`
(Q-share), `content/tags.jsonl`(Q-tag). 링크와 패치의 id는 영문 소문자·숫자·하이픈(`[a-z0-9-]+`)이다. **빌드**는
저장소에서 `npm run build`이다(Q-build).

Decided (owner, `source:tb-01`, `source:tb-02`, `source:tb-04`; 제안 `source:tb-03`): 글에 붙는 기록은 관계형 DB의 표처럼 다룬다.
기록 종류마다 JSONL 파일 하나가 표이고, 한 줄이 JSON 객체 하나(행 하나, 사건 하나)다. 표에는 줄을 덧붙이기만 하고 지난 줄을
고치지 않는다 — 이력이 표 자체에 남는다. 지금 살아 있는 링크, 지금 달린 태그 같은 현재 상태는 빌드가 표에서 계산한다. 빈 줄은
무시하고, 표 파일이 없으면 그 기록이 없는 것이다. 한 줄이 JSON 객체가 아니거나 그 표의 규칙에 어긋나면 빌드 오류이고, 오류 줄은
`<표 파일 경로>:<줄 번호>`를 포함한다.
**본문**은 글 파일의 헤더 다음 텍스트이고, **적용된 본문**은 그 글의 패치를 모두 적용한 뒤의 본문이다.

## Q-build — 생성기와 출력

Concept: `site-build`.

Decided (owner, `source:as-01`, `source:as-03`, `source:as-05`; 제안 `source:as-02`, `source:as-04`; 아래의 옛 결정 "표준 라이브러리만
쓰는 Python 생성기"와 `source:rf-01`의 `build.py`·`sitegen/` 구조를 바꿈): 생성기는 Astro 프로젝트다. 외부 패키지를 쓸 수 있고
언어도 Python에 묶이지 않는다. 페이지는 템플릿으로 짓는다 — 공통 틀 하나를 모든 페이지가 이어받고, 되풀이되는 조각은 컴포넌트다.

- **실행:** 저장소에서 처음 한 번 `npm install`, 그 뒤 `npm run build`. `npm run build`는 `node scripts/build.mjs`이고, 이 스크립트는
  실행한 현재 작업 디렉터리의 `content/`를 읽어 같은 디렉터리의 `docs/`를 통째로 다시 만든다(Astro 프로젝트 자체는 스크립트가 있는
  저장소다). `package.json`과 잠금 파일(`package-lock.json`)은 커밋하고 `node_modules/`는 무시한다.
- **구조:** `src/layouts/BaseLayout.astro`(문서 머리, 상단 메뉴 띠, 본문 자리)를 피드·글·소개·태그 페이지(`src/pages/`)가 모두
  이어받는다. 피드 상자, 공유 배지, 주석, 이 글을 가리키는 글, 태그 클라우드, 패치 보기 같은 조각은 `src/components/`의
  컴포넌트다. 기록 표와 글 파싱, 마크다운 렌더, 패치 적용, 링크 앵커 같은 이 사이트만의 규칙은 TypeScript 모듈 `src/lib/`에 있다.
  규칙 자체(이 문서의 각 절)는 바뀌지 않는다.
- **정적 파일:** CSS와 자바스크립트(`site.css`, `time.js`, `zoom.js`)와 공유 곳의 로고(`brands/`)는 `public/assets/`에 있고
  `docs/assets/`로 바이트 그대로 복사된다. Astro의 번들링·범위 지정 스타일·인라인 스크립트는 쓰지 않는다 — 페이지가 싣는 파일은 이
  정적 파일뿐이고, 모든 링크는 지금처럼 각 페이지 위치 기준의 상대 경로다. 외부에서 가져오는 스크립트·글꼴·스타일은 없다(패키지는
  빌드할 때만 쓴다).
- **출력:** `docs/index.html`(피드), 글마다 `docs/p/<id>/index.html`, `docs/about/index.html`(소개, Q-about),
  `docs/tags/<태그>/index.html`(Q-tag), `docs/assets/`, `docs/images/`(`content/images/`의 복사본), 빈 파일 `docs/.nojekyll`. 그 밖의
  파일(예: Astro의 `_astro/`)은 만들지 않는다. 같은 입력이면 출력이 바이트 단위로 같다(빌드 시각 같은 값은 넣지 않는다).
- **오류:** 입력이 잘못되면 빌드는 stderr에 잘못된 파일의 경로를 포함한 줄을 쓰고 종료 코드 1로 끝나며, `docs/`는 빌드 전 그대로
  남는다 — Astro는 출력 폴더를 먼저 비우므로, 빌드 스크립트가 새 출력을 임시 디렉터리에 만든 뒤 교체한다. 잘못된 입력은 이 문서의
  각 절이 "빌드 오류"라고 적은 경우다.
- **본문 문법:** Q-post를 따른다. 옮기는 동안은 부분집합 그대로였고(`source:as-04`), 옮긴 뒤 `source:md-03`으로 넓혔다.
- **배포:** 옮기는 동안에는 지금처럼 로컬에서 빌드한 `docs/`를 커밋하고 Pages가 main의 `/docs`를 서비스한다(`source:as-04`의
  권고). GitHub Actions 배포는 나중에 따로 정한다.
- **테스트:** 계약 테스트는 `tests/`의 Python unittest로 남고 `python3 -m unittest discover -s tests`로 돈다(`source:as-04`의
  권고). 테스트는 빌드를 밖에서 실행하고 결과만 본다 — `tests/support.py`가 새 임시 디렉터리를 작업 디렉터리로 두고
  `node <저장소>/scripts/build.mjs`를 실행한다. 정적 파일을 바이트 그대로 비교하는 테스트의 원본은 `public/assets/`다.
- **엔진:** Node `>=22`(hunsu.json `engines`), 테스트용 Python `>=3.9`.
- **의존성 (technical, session — astro-frame 첫 시도를 되돌린 뒤):** 페이지 HTML은 Astro가 `src/pages/`와 `src/layouts/`의
  템플릿으로 실제로 만든다. `scripts/build.mjs`가 옛 Python 생성기(`build.py`·`sitegen/`)를 부르거나 HTML을 Astro 밖에서 문자열로
  짓는 것은 이 결정을 따르지 않은 것이다. 패키지(`astro`, `markdown-it`)는 세션이 네트워크로 설치해 `package.json`과
  `package-lock.json`에 커밋해 두었고 `node_modules/`에 있다 — 작업자는 네트워크 없이 이것으로 빌드한다. 새 패키지가 더 필요하면
  손으로 잠금 파일을 만들지 말고 보고의 blocked로 알린다. Decided after build (astro-frame-2, technical, delegated): `sitegen/assets/`는
  파일 시스템 이동으로 `public/assets/`에 옮긴다(작업자 샌드박스에서 `git mv`가 막힘 — git은 커밋 때 이름 바꾸기로 본다).
- **템플릿 (technical, session — astro-frame-2를 받은 뒤):** 페이지의 마크업은 `.astro` 템플릿과 컴포넌트가 짓는다. `src/lib/`는 글과
  기록 표를 읽고 계산한 데이터(글 목록, 링크, 패치 영역, 공유, 태그)와 본문 마크다운의 HTML만 돌려주며, 피드 상자·항목 바닥글·공유
  배지·태그 클라우드·주석·이 글을 가리키는 글·패치 보기 같은 마크업을 문자열로 짓지 않는다. 본문 HTML은 `set:html`로 넣는다.

Decided (owner, `source:as-03`, 제안 `source:as-02`): 모든 페이지 맨 위에 같은 폭의 메뉴 띠가 있고, "피드"와 "소개"는 어느 페이지에서나
화면의 같은 자리에 있다. Decided (technical, session): 띠는 `<header class="site-header"><nav class="site-nav"><a …>피드</a><a …>소개</a></nav></header>`이고
화면 폭 전체에 걸친다. 띠 안쪽(`.site-nav`)과 그 아래 본문 틀(`.frame`)은 모든 페이지에서 같은 최대 폭 `70rem`, 가운데 정렬, 좌우
여백 `1.25rem`이다. 본문 칸은 틀의 왼쪽에 붙은 `48rem`이고, 피드는 넓은 화면(`64rem` 이상)에서 그 오른쪽에 태그 클라우드 칸을
둔다 — 페이지마다 틀의 폭은 바뀌지 않는다. 스크롤바가 생겨도 자리가 밀리지 않도록 `html { scrollbar-gutter: stable; }`이다.

Decided (owner, `source:as-04`, `source:as-05`): 옮기는 순서는 셋이다 — (1) 틀: Astro 뼈대, 빌드 스크립트, `BaseLayout`과 상단 띠,
글·피드·소개 페이지; (2) 고유 로직: 기록 표, 링크, 패치와 패치 보기, 공유, 태그; (3) 정리: `build.py`·`sitegen/` 삭제, README,
hunsu.json 엔진, 망상 관계. 조각마다 계약 테스트가 먼저 있고, 모든 조각이 끝나면 테스트 전부가 새 빌드로 통과한다. 옮기기 전과
후의 `docs/`는 상단 띠와 페이지 틀의 마크업·CSS만큼만 다르다.

(옛 결정, 위의 결정으로 바뀜) `python3 build.py`는 `content/`를 읽고 `docs/`를 통째로 다시 만든다. 표준 라이브러리만 쓴다.
`build.py`는 진입점이고 나머지는 패키지 `sitegen/`(`records`, `markdown`, `patches`, `pages`, `output`)에 있으며 CSS와
자바스크립트는 `sitegen/assets/`의 파일이다(`source:rf-01`, `source:rf-03`). 테스트는 `build.py`를 `sys.executable`로 실행하고,
도우미는 `tests/support.py`에 있다. 패키지 이름이 `site/`가 아니라 `sitegen/`인 것은 표준 라이브러리 모듈 `site`를 가리지 않기
위해서였다.

Decided (owner, `source:about-06`, `source:about-08`): 주소는 폴더 방식이다 — 첫 화면 `/`, 글 `/p/<id>/`, 소개 `/about/`.
사이트가 만드는 링크는 파일 이름(`index.html`, `.html`)을 쓰지 않고 폴더로 건다: 피드로는 `./`(글 페이지에서 `../../`,
소개에서 `../`), 글로는 `p/<id>/`, 소개로는 `about/`. 공통 파일과 이미지도 각 페이지 위치 기준의 상대 경로다. 첫 화면은 피드이고,
모든 페이지 위쪽 메뉴에 "피드"와 "소개" 링크가 항상 있다.

Decided (technical, delegated): 저장소 루트의 기존 `index.html`은 `docs/`로 옮겨지지 않는다 — 피드가 새 첫 화면이다. Pages의
서비스 위치를 main의 `/docs`로 바꾸는 것은 푸시할 때 소유자가 한다.

## Q-post — 글 하나

Concept: `post`, `post-type`, `tag`.

글 파일은 헤더와 본문으로 이루어진다. 헤더는 파일 첫 줄부터 빈 줄 전까지의 `key: value` 줄들이다.

- `written`: 작성 시각. `YYYY-MM-DDTHH:MM:SSZ` 형식의 UTC. 반드시 있고, 글의 `<id>`와 같은 시각이다.
- `type`: `short`(짧은 글), `medium`(중간 글), `long`(긴 글) 중 하나. 반드시 있다. 유형은 쓰기 전에 고르는 것이며,
  빌드는 분량으로 유형을 판단하지 않는다.
- `title`: 제목. `short`에서는 있으면 빌드 오류, `medium`과 `long`에서는 선택.
Decided (owner, `source:tg-01`): 태그는 헤더에 쓰지 않는다 — 태그를 달고 떼는 일은 시각과 이유가 있는 사건으로 표에 남긴다(Q-tag).
헤더의 `tags`는 그 밖의 키처럼 빌드 오류다.

Decided after quibble (s1-tests, technical, delegated): 키와 값의 앞뒤 공백은 무시하고, 키는 대소문자를 구분한다. 콜론이 없는
헤더 줄과 같은 키가 두 번 나오는 헤더는 빌드 오류다.

그 밖의 키, 형식이 틀린 `written`, 목록에 없는 `type`, 두 글이 같은 `<id>`(파일 이름)인 경우는 빌드 오류다.

Decided (owner, `source:id-01`, `source:id-02`, `source:id-03`, `source:id-04`): 글의 `<id>`, 곧 글 파일의 이름은 작성 시각이다 —
`YYYYMMDD-HHMMSS`(UTC, 예: `20260924-075921`). 제목은 늘 있는 것이 아니고 글에 붙은 메타데이터 중 하나일 뿐 정체성이 아니며, 글의
정체성은 태그, 연결 관계, 수정 내역에 있어 파일 이름에 담을 수 없다. 관례가 아니라 빌드가 지킨다: `<id>`가 이 형식이 아니거나
`written`과 다른 시각이면 빌드 오류이고, 오류 줄은 그 글 파일의 경로를 포함한다. 이미지만 있는
글은 본문이 이미지 한 줄인 글이다.

Decided (owner, `source:plan-11`): 본문이 빈 글은 빌드 오류다.

본문은 Markdown의 부분집합이다: 빈 줄로 나뉜 문단, `#`/`##`/`###` 제목, `- ` 목록, `> ` 인용, `**굵게**`, `*기울임*`,
`` `코드` ``, 이미지 `![설명](images/파일)`. 이미지 경로가 `content/images/`에 없으면 빌드 오류다. 본문의 HTML은 글자로
보인다(태그로 해석되지 않는다).

Decided (owner, `source:md-03`, 요청 `source:md-01`, 제안 `source:md-02`; 위의 부분집합을 넓힘): 본문은 표준 마크다운(CommonMark)
전부에 GFM의 표와 취소선(`~~글자~~`)을 더한 문법이다 — 번호 목록, 중첩 목록, 인용 안의 목록과 문단, 코드 블록(```` ``` ````와
들여쓰기), 제목 `#`~`######`, 가로줄 등. 본문의 HTML은 지금처럼 글자로 보인다. 각주와 자동 링크(주소 글자를 저절로 링크로)는 없다.
Decided (technical, session): 본문은 markdown-it(`commonmark` 설정 + `table`, `strikethrough`, `html: false`, `linkify: false`)으로
렌더한다. 아래의 기존 규칙은 그대로 지킨다:
- 문단과 인용 안에서 줄을 바꾸면 화면에서도 줄이 바뀐다(`breaks: true`, `source:br-01`).
- 그림은 `![설명](images/파일)`과 `![설명|N](images/파일)`만 된다 — 경로가 `images/`로 시작하지 않거나 파일이 없거나 `|0`이면 빌드
  오류다. 글 페이지와 소개 페이지의 그림은 `image-zoom` 링크로 감싸진다.
- 링크는 모든 모양(`[글자](주소)`, 참조 링크 `[글자][이름]`, `<https://…>`)이 바깥 링크 규칙을 따른다 — 주소가 `http://`·`https://`로
  시작하지 않으면 빌드 오류이고, 마크업은 `<a href="주소">글자</a>`다.
- 코드(인라인 코드와 코드 블록) 안의 글자는 해석하지 않는다 — 그 안의 `[글자](주소)`나 `![…](…)`는 글자다. 글 사이 링크의 앵커(Q-link)가
  코드 안에 들거나 코드와 겹치면 빌드 오류이고 오류 줄은 그 링크의 `created` 줄이다. 패치 보기의 영역이 코드의 일부만 덮으면
  빌드 오류이고 오류 줄은 그 패치의 줄이다(코드 전체를 덮거나 겹치지 않으면 된다).
- 피드의 80자, 제목 없는 글의 제목 자리, 링크·주석 목록의 글 이름은 전과 같이 첫 문단(`<p>`)의 화면 글자에서 센다.
Decided after verify (md-build 세 번째 반려, technical, session): 참조 링크는 CommonMark의 세 모양(`[글자][이름]`, `[글자][]`,
`[글자]`) 모두 바깥 링크 규칙을 따른다. 표의 정렬 구분자(`:--`, `:-:`, `--:`)는 그 칸의 `style="text-align: left|center|right"`가
된다. 패치 보기의 영역이 그림 표시 `![…](…)`의 일부만 덮으면(예: 설명 글자만 바꾸는 패치) 빌드 오류이고 오류 줄은 그 패치의 줄이다 —
그림 전체를 덮거나 겹치지 않으면 된다. 렌더에 쓰는 내부 표식은 본문에 나올 수 없는 글자(NUL 같은 제어 문자)만 쓴다 — 사용자가 쓴
어떤 글자도 표식으로 잘못 읽히지 않는다.
Decided after verify (md-build 네 번째 반려, technical, session): 본문(패치가 넣은 글자 포함)에 제어 문자(탭과 줄바꿈 밖의
U+0000–U+001F, U+007F)가 있으면 빌드 오류이고 오류 줄은 그 글 파일(패치가 넣었으면 그 패치의 줄)이다 — 내부 표식과 겹칠 글자가 본문에
들어오지 않는다. 참조 링크의 정의 줄(`[이름]: 주소`)은 링크가 아니며 링크 순번이나 겹침 검사의 대상이 아니다(주소 검사는 그 정의를 쓰는
링크에서 한다).

Decided (owner, `source:el-02`, 제안 `source:el-01`; Q-about의 "바깥 링크는 소개 페이지에서만"을 바꿈): 글 본문에서도 바깥 링크
`[글자](주소)`가 링크가 된다 — 모든 유형의 글에서, 소개 페이지와 같은 규칙으로. 주소는 `http://` 또는 `https://`로 시작해야 하고,
아니면 빌드 오류이며 오류 줄은 그 글 파일의 경로를 포함한다. Decided (technical, session): 바깥 링크는 소개 페이지와 같은
`<a href="주소">글자</a>`가 된다(같은 탭에서 열린다). 글자 안의 서식은 해석하지 않는다. 화면 글자(피드의 80자, 링크·주석 목록의
글 이름)에는 `글자`만 들어가고 주소는 들어가지 않는다. 피드에 본문이 나오는 짧은 글에서는 바깥 링크가 공유 배지처럼 상자 링크
위에 놓여 따로 눌린다. 글 사이 링크의 앵커(Q-link)가 바깥 링크 `[글자](주소)`의 일부와 겹치거나 그 안에 들면 빌드 오류이고, 오류
줄은 그 링크의 `created` 줄을 가리킨다(링크 안에 링크를 넣지 않는다). 패치(Q-patch)는 적용된 본문을 바꾸는 것이므로 바깥 링크를
넣거나 고치거나 지울 수 있다 — 바깥 링크는 패치가 모두 적용된 본문에서 해석된다. 다만 패치 보기의 영역(Q-patch-view)이 적용된
본문의 바깥 링크 `[글자](주소)`의 일부만 덮으면 빌드 오류이고, 오류 줄은 그 패치의 줄을 가리킨다(영역이 링크 전체를 덮거나 링크와
겹치지 않으면 된다).

Decided (owner, `source:el-03`): 본문의 링크는 파란색으로 보여 글자와 구별된다. Decided (technical, session): 본문(`.body` — 글
페이지, 소개 페이지, 피드에 나오는 짧은 글 본문)의 모든 링크 — 바깥 링크와 글 사이 링크의 앵커, 주석 번호 — 가 `#1d4ed8`이다. 메뉴,
피드 상자, 태그, 공유 배지, 주석·"이 글을 가리키는 글" 목록의 글자는 전과 같다.

Decided (owner, `source:zm-03`, 요청 `source:zm-01`, 제안 `source:zm-02`): 글 페이지와 소개 페이지 본문의 그림을 누르면, 페이지를
떠나지 않고 어두운 배경 위에 원본 파일이 화면 크기에 맞춰 크게 보인다. 배경을 누르거나 Esc를 누르면 닫힌다. 피드에서는 지금처럼
상자를 누르면 글로 간다(피드의 그림에는 이 동작이 없다). Decided (technical, session): 본문의 그림은 원본 파일로 가는 링크
`<a class="image-zoom" href="<그림의 src와 같은 주소>"><img …></a>`로 감싸진다 — 스크립트가 없으면 이 링크가 원본 파일을 같은 탭에서
연다. 스크립트 `assets/zoom.js`(`public/assets/zoom.js`를 바이트 그대로 복사)가 글 페이지와 소개 페이지에만 `defer`로 실린다. 이
스크립트는 `.image-zoom` 링크의 기본 동작을 막고, 원본 그림 하나를 담은 겹침 층(`.zoom-overlay`, 화면 전체, 어두운 반투명 배경,
그림은 `max-width: 100vw; max-height: 100vh` 안에서 비율 유지)을 띄운다. 겹침 층 어디를 눌러도, Esc를 눌러도 닫힌다. 그림의 표시
너비 `|N`은 본문에서의 크기만 정하고, 겹침 층에서는 원본이 화면에 맞춰진다. 그림이 바깥 링크 안에 있는 경우는 없다(바깥 링크의
글자에는 서식을 해석하지 않는다). Decided after build (zoom-build, technical, delegated): 겹침 층의 배경은 `rgba(0, 0, 0, 0.7)`이다. Decided (technical, session): 겹침 층은 `z-index: 10`으로 본문의 다른 층(패치 이력 상자, 공유 배지) 위에 놓인다.

Decided (owner, `source:img-01`, `source:img-03`): 이미지의 표시 너비를 정할 수 있다 — `![설명|N](images/파일)`에서 `N`은 CSS
픽셀 단위의 너비이고 높이는 비율대로 따른다. 원본 파일은 그대로다. `N`이 없으면 지금처럼 원본 크기(칸 너비를 넘지 않음)로 보인다.
Decided (technical, session): `N`은 1부터 9999까지의 정수이고 `<img … width="N">`이 된다. 설명 끝의 `|` 뒤가 정수가 아니면 설명의
일부로 본다. `|0`은 빌드 오류다. 설명(`alt`)에는 `|N`이 들어가지 않는다 — 피드의 80자처럼 이미지 설명을 글자로 쓰는 곳도 같다.
소개 페이지에서도 같다(Q-about).

Decided (owner, `source:br-01`, `source:br-03`, 제안 `source:br-02`): 문단과 인용 안에서 줄을 바꾸면 화면에서도 줄이 바뀐다 —
파일에 보이는 대로 보인다. 빈 줄은 지금처럼 문단을 나눈다. Decided (technical, session): 줄바꿈은 `<br>`이 된다. 피드의 짧은 글
본문도 같다. 80자를 세는 화면 글자는 전과 같다(줄바꿈 한 글자).

글 페이지 `docs/p/<id>/index.html`은 제목(있으면), 작성 시각, 태그, 본문을 보여준다.

Decided (owner, `source:plan-11`; 태그 부분은 `source:tg-04`로 바뀜): 태그는 글 페이지에 나오고, 태그별 페이지로 가는 링크다(Q-tag).
Decided (owner, `source:fd-04`; `source:plan-11`의 "유형 이름을 작게 표시한다"를 바꿈): 유형 이름(짧은 글/중간 글/긴 글)은 화면에
표시하지 않는다. 유형은 쓰기 전에 고르는 것이고, 피드에서 무엇을 보여줄지(Q-feed)를 정할 뿐이다.

## Q-feed — 첫 화면

Concept: `feed`.

`docs/index.html`은 모든 글을 작성 시각의 최신순으로 한 줄에 보여준다(유형별로 나누지 않는다. 글의 `<id>`가
작성 시각이라 두 글의 시각이 같을 수 없다). 짧은
글은 본문 전체를 보여주고, 중간·긴 글은 제목과 시각을 보여준다. Decided (owner, `source:plan-11`): 제목이 없는 중간·긴
글은 제목 자리에 본문 첫 문단의 앞 80자(잘렸으면 `…`)를 보여준다. Decided after quibble (s1-tests, technical, delegated): 80자는 적용된 본문의 첫 문단을 HTML로 만든 뒤의 화면 글자(서식
기호와 태그를 뺀 글자)에서 유니코드 문자 단위로 센다. 이미지만 있는 첫 문단은 이미지 설명(alt)을 글자로 쓴다. 모든 항목은
그 글의 페이지로 가는 링크를 가진다. 피드의 본문은 적용된 본문이다.

Dismissed after quibble (s1-tests): "checks가 비어 있다"는 다섯 건 — 트집 작업은 계약 테스트를 쓰는 작업이라 그 테스트가 검사이고,
`s1-build`가 `python3 -m unittest discover -s tests`로 돌린다.

Decided (owner, `source:fd-01`, `source:fd-02`, `source:fd-03`): 피드 항목의 양식 —
- 항목마다 분리된 상자(`<article class="feed-item">`)다.
- 제목은 있을 때만 맨 위에 굵게 나온다. 짧은 글에는 제목 줄이 없다(제목 자리에 `<id>`를 쓰지 않는다).
  제목이 없는 중간·긴 글은 위의 80자가 제목 자리에 온다.
- 짧은 글은 요약 없이 본문 전체를 보여준다. 짧은 글이기 때문이다.
- 항목 하단(`<footer class="item-footer">`)에 작성 시각(Q-time의 독자 현지 시각)이 나오고, 그 뒤에 공유 배지가 붙는다(Q-share).
Decided (owner, `source:fd-04`; 위의 유형 이름과 "시각이 링크"를 바꿈): 시각은 링크가 아니다. 항목 상자 전체가 그 글의 페이지로 가는
링크다 — 글을 누르면 이 글과 연결된 다른 글들과 각종 정보(주석, 이 글을 가리키는 글, 패치, 공유)로 들어간다. 상자 안의 공유
배지는 따로 눌려 공유한 글로 간다. Decided (technical, session): 상자 링크는 상자를 덮는 투명한 링크(`<a class="item-link">`)이고,
배지는 그 위에 놓인다(링크 안에 링크를 넣지 않는다). 제목이 있으면 제목이 그 링크의 이름이 되고, 없으면 "글 보기"다.
- 본문 글씨는 읽기 좋게 키운다(18px, `1.125rem`).
Decided (technical, session): 글 페이지도 같은 하단(작성 시각, 공유 배지)을 본문 아래에 둔다 — 디자인 일관성(`source:about-09`).

## Q-time — 시각 표시

Concept: `local-time`.

화면의 모든 시각은 `<time datetime="YYYY-MM-DDTHH:MM:SSZ">` 요소로 나오며, 요소의 글자는 UTC로
`YYYY-MM-DD HH:MM UTC`다. 페이지의 자바스크립트가 이를 독자 브라우저의 시간대로 바꿔 `YYYY-MM-DD HH:MM`로 보여주고, 요소의
`title`에 UTC 표기를 남긴다. 자바스크립트가 없으면 UTC 글자가 그대로 보인다.

Decided after the verifier (s1-build-4, technical, delegated): 현지 시각으로 바꾼 연도가 0001–9999 밖이면(예: UTC+14에서
`9999-12-31T23:59:59Z`) 바꾸지 않고 UTC 글자와 `title`을 그대로 둔다. 숫자는 항상 ASCII다.

## Q-ui — 화면 언어

Concept: `ui-language`.

메뉴, 버튼, 안내 문구 등 사이트가 만드는 글자는 한국어다. `<html lang="ko">`.

## Q-link — 주석으로 거는 링크

Concept: `link`.

링크 표 `content/links.jsonl`의 한 줄은 링크 사건 하나다. 링크를 거는 줄은 `{"link": <링크 id>, "from": <글 id>, "to": <글 id>,
"anchor": <문자열>, "action": "created", "at": <UTC 시각>, "why": <문자열>}`이고, 그 뒤의 사건은 `{"link", "action":
"reason-changed" | "removed", "at", "why"}`다. 한 링크의 첫 사건은 `created`이고 `created`는 한 번뿐이며, 사건의 시각은
줄 순서대로 내려가지 않는다. 현재 사유는 마지막 `created` 또는 `reason-changed`의 `why`다. 마지막 사건이 `removed`면 그 링크는
화면에 나오지 않지만 기록은 남는다(변경 기록은 관리하되 화면에 보이지 않는다). 키 집합이 위와 다르거나, `created`가 아닌 사건이
먼저 오거나, `created`가 두 번이거나, 시각이 내려가면 빌드 오류이고 오류 줄은 그 표의 줄을 가리킨다.

`anchor`는 `from` 글의 적용된 본문에 그대로 나오는 문자열이며, 정확히 한 번 나와야 한다(없거나 두 번 이상이면 빌드
오류). 글 페이지에서 그 문자열은 `to` 글로 가는 링크가 되고, 바로 뒤에 위첨자 `[n]`이 붙는다. `n`은 그 글 안에서 앵커가
나오는 순서로 1부터 매긴다. 본문 아래 "주석" 목록의 `n`번 항목은 `to` 글의 제목(없으면 첫 문단 앞 80자)과 현재 사유,
링크를 건 시각(`created`의 `at`)을 보여준다. `from`이나 `to`가 없는 글이거나, 앵커가 없거나 두 번 이상 나오면 빌드
오류이고 오류 줄은 그 링크의 `created` 줄을 가리킨다.

Decided after quibble (s2-tests, technical, delegated): 앵커 글자는 `<a href="../<to>/">…</a>`가 되고 바로 뒤에
`<sup><a href="#fn-<n>">[n]</a></sup>`가 붙는다. "주석" 목록은 `<ol>`이며 `n`번 항목의 `id`는 `fn-<n>`이다. 글 페이지 사이의
링크는 상대 경로다(주소 형식은 Q-build의 폴더 방식 주소).

Decided (owner, `source:plan-11`): 받는 쪽 글(`to`)의 페이지 아래에 "이 글을 가리키는 글" 목록을 두고, 각 항목은 `from`
글의 제목(없으면 첫 문단 앞 80자)과 현재 사유를 보여준다.

Decided after quibble (s2-tests, technical, delegated): 이 목록은 링크를 건 시각(`created`의 `at`)의 최신순이고, 같으면 링크
`id` 순이다. 마지막 이벤트가 `removed`인 링크는 넣지 않는다. 가리키는 글이 없으면 목록을 두지 않는다.

Dismissed after quibble (s2-tests): "checks가 비어 있다" — 트집 작업의 테스트가 검사이고 `s2-build`가 돌린다.

## Q-patch — 패치

Concept: `patch`.

패치 표 `content/patches.jsonl`의 한 줄은 패치 하나다: `{"id", "post": <글 id>, "at": <UTC 시각>, "why": <문자열>, "op":
"replace" | "insert-before" | "insert-after" | "delete", "anchor": <문자열>, "text": <문자열>}` (`delete`에는 `text`가 없다). 한 글의 패치는 `at` 오름차순(같으면 `id`
순)으로 차례로 적용되고, 각 패치의 `anchor`는 그때까지 적용된 본문에 정확히 한 번 나와야 한다(아니면 빌드 오류). 그래서 앞선
패치가 만든 글에 패치를 붙일 수 있다. `replace`는 앵커를 `text`로 바꾸고, `insert-before`/`insert-after`는 앵커 앞/뒤에
`text`를 넣고, `delete`는 앵커를 지운다. 패치는 한 글 안에서만 작용하며 길이 제한은 없다. 글 파일 자체는 패치로 바뀌지
않는다(원문은 남는다).

Decided after quibble (s3-tests, technical, delegated; 표로 옮김 `source:tb-04`): `id`는 문자열이며 표 안에서 한 번만 나온다.
JSON 객체가 아니거나, 키 집합이 위와 다르거나, `op`가 목록에 없거나, `delete`에 `text`가 있거나 다른 `op`에 없거나, `at`이
`written`과 같은 형식이 아니거나, `post`가 없는 글을 가리키거나, `id`가 겹치거나, 앵커가 그 순간의 본문에 정확히 한 번 나오지
않으면 빌드 오류이고, 오류 줄은 그 패치의 줄(`content/patches.jsonl:<줄 번호>`)을 가리킨다. 같은 `at`의 패치는 `id`의 문자열 순서로 적용한다. 앵커는 패치를 적용하기 전 그 순간의
본문(글 파일의 본문에 앞선 패치를 적용한 것)에서 찾으므로, 다른 글이나 글 경계 밖을 가리킬 수 없다.

Decided (owner, `source:plan-05`): 올린 글을 고치는 일반적인 방법은 패치를 더하는 것이고, 글 파일을 직접 고치는 일은 이
계획의 범위 밖이다(완전 삭제 `erasure`의 절차는 열린 질문이 답해진 뒤에 정한다).

## Q-patch-view — 패치 보기

Concept: `patch-view`.

패치가 하나 이상 있는 글의 페이지에는 "패치 보기" 토글 버튼이 있다. 켜면 패치가 바꾸거나 넣은 영역이 테두리(아웃라인)로
표시되고, 지운 자리에는 표시가 남는다. 그 영역에 마우스를 올리면 그 자리에 적용된 패치의 이력 — 각 패치의 시각(독자 현지
시각), 사유, 종류, 이전 글자 — 이 보인다. 끄면 표시가 사라지고 적용된 본문만 보인다. Decided (owner, `source:plan-11`): 기본은 꺼짐이다. 겹치는 패치 같은 엣지
케이스는 쓰면서 대응한다(열린 질문 `patch-view-edges`).

Decided after quibble (s3-tests, technical, delegated): 한 패치의 영역은 그 패치가 넣은 글자다 — `replace`와 `insert-*`는 `text`
전체, `delete`는 지운 자리의 표시 하나(패치 보기를 끄면 자리를 차지하지 않고, 켜면 작은 표시로 보인다 — 계약을 정정, s3-build-4 검증 후). 이후의 패치가 그 영역의 일부를 다시 바꾸면, 적용된 본문의 각 글자는 마지막으로
그 글자를 만든 패치의 영역에 속하고, 앞선 패치의 영역은 남은 글자만큼 줄어든다(모두 사라지면 표시도 없다). 한 영역의 이력은 그
영역의 글자를 만들거나 바꾼 패치들을 시각 순으로 보여준다. 각 항목의 시각은 Q-time의 `<time>` 표기와 같은 규칙으로 독자 현지
시각이 되고, "이전 글자"는 `replace`와 `delete`에서는 앵커의 글자, `insert-*`에서는 없음("새로 넣음")이다. 이는 첫 기준이며,
실제로 쓰다 드러나는 엣지 케이스는 `patch-view-edges`에서 다룬다.

Dismissed after quibble (s3-tests): "checks가 비어 있다" 열한 건 — 트집 작업의 테스트가 검사이고 `s3-build`가 돌린다.

## Q-readme — 글쓴이의 안내서

Concept: `post`, `site-build`.

저장소 루트의 `README.md`는 이 사이트에 글을 올리는 사람을 위한 한국어 안내서다. 새 글을 쓰는 법(파일 위치와 이름, 헤더의
`written`·`type`·`title` 각각의 규칙과 예시, 본문에 쓸 수 있는 문법, 이미지 넣는 법), 링크를 거는 법(링크 파일의 모양,
사유를 바꾸거나 지우는 법), 패치를 붙이는 법(패치 파일의 모양, `op` 네 가지), 사이트를 만드는 명령(처음 한 번 `npm install`, 그 뒤 `npm run build`)과 결과가
생기는 곳(`docs/`), 빌드 오류가 났을 때 무엇을 보면 되는지를 담는다. 안내서의 예시를 그대로 따라 한 글·링크·패치는 빌드 오류 없이
만들어진다. 안내서에 적힌 규칙은 이 계획서의 규칙과 어긋나지 않는다.

Decided after quibble (readme-tests, technical, delegated): 한국어 — 코드 블록 밖 본문 글자 중 한글이 절반 이상이다. 담는다 —
새 글, 링크, 패치, 빌드 각각에 `##` 절이 있고, 새 글 절에 `written`·`type`·`title`, 패치 절에 `op` 네 가지, 빌드 절에
`npm run build`와 `docs/`, 그리고 빌드 오류가 stderr에 파일 경로를 담은 한 줄로 나온다는 설명이 있다. 예시는 정보 문자열에 종류와
경로를 적은 코드 블록이다: ```` ```post content/posts/<id>.md ````, ```` ```link content/links.jsonl ````,
```` ```patch content/patches.jsonl ````(표로 옮김 `source:tb-04` — 블록의 줄들이 그 표의 줄들이다). 안내서에는 태그를 달고 떼는 절과
```` ```tag content/tags.jsonl ```` 예시도 있다. 테스트는 그 블록들을 그대로 임시 사이트에 쓰고 빌드해, 글 페이지가 생기고, 링크의
`[n]`이 붙고, 패치가 적용된 글자가 보이는지 본다. 계획서와 어긋나지 않는다 — 예시가 실제 빌드로 오류 없이 빌드되는 것이 그
증거다(빌드가 이 계획서의 규칙을 강제한다); 그 밖의 문장 대 문장 일치는 기계로 관찰하지 않는다(non-claim).

Decided by the builder (readme-3, technical, accepted as delegated): 안내서는 계획서의 어휘(절 id, 개념 이름)를 쓰지 않고, 제목은 글쓴이가
하는 일로 붙인다. 빌드 절의 제목은 `사이트 만들기 — 빌드`다.

Decided (technical, session): 안내서에는 소개 페이지를 쓰는 법(`content/about.md`, 헤더 없음, 바깥 링크)도 `##` 절로 담는다.
예시는 ```` ```about content/about.md ```` 블록이며, 테스트는 다른 예시처럼 그대로 빌드해 `docs/about/index.html`이 생기는지 본다.

## Q-about — 소개 페이지

Concept: `about`.

Decided (owner, `source:about-01`, `source:about-03`): 사이트에 소개 페이지를 하나 둔다. 소개 글은 `content/about.md`에 쓰고, 긴작업 org를 한국어로
짧게 설명하고 그 org로 가는 링크를 건다. 아바타와 org 로고 이미지를 쓴다. 소개 글은 주인이 쓰는 글이다 — 사이트를 만드는 일(이 절의 빌드)과 달리, 글을 쓰고 고치는
일은 run 밖의 절차다.

Decided (owner, `source:about-09`; 옛 첫 화면을 따른 어두운 가운데 정렬(`source:about-03`)을 바꿈): 디자인은 일관되어야 한다 — 소개
페이지는 흰 배경에 글 페이지와 같은 모양이다.

`content/about.md`는 헤더가 없고 파일 전체가 본문이다. 본문 문법은 Q-post와 같고, 여기에 바깥 링크 `[글자](주소)`가 더해진다.
주소는 `http://` 또는 `https://`로 시작해야 한다. 바깥 링크는 글 본문에서도 같은 규칙으로 링크가 된다(Q-post, `source:el-02`).
`content/about.md`는 글이 아니다 — 글 목록, 피드, 링크와 패치의 대상에 들지 않는다.

빌드는 `docs/about/index.html`을 만든다. 제목은 "소개"이고, 글 페이지와 같은 스타일(흰 배경, 왼쪽 정렬)로 보인다.
이미지는 글과 같이 `content/images/`에서 온다. 모든 페이지 위쪽 메뉴에 "피드"와 "소개" 링크가 붙는다(Q-build).
Decided (owner, `source:about-06`): 소개 글은 반드시 있다 — `content/about.md`가 없으면 빌드 오류이고, 오류 줄은 `content/about.md`를 포함한다.
본문이 비었거나 바깥 링크의 주소가 `http://`·`https://`로 시작하지 않으면 빌드 오류이고, 오류 줄은 `content/about.md`를 포함한다.

Decided (technical, session): 바깥 링크는 `<a href="<주소>">글자</a>`이며 글자는 서식 없이 글자로 보인다. 소개 페이지의 본문은 글
페이지처럼 `<article class="post">` 안의 `<div class="body">`에 놓이고, 소개 페이지만의 스타일은 없다.

## Q-share — 공유 기록과 배지

Concept: `share`.

Decided (owner, `source:fd-01`, `source:fd-03`; 제안 `source:fd-00`): 글이 다른 곳(X, 스레드, 링크드인 등)에 공유되면 그 기록을
남기고, 피드 항목과 글 페이지 하단에 곳마다 흑백 아이콘 배지를 단다. 배지는 그 공유 글로 가는 링크다. 아직 아무 곳에도 공유하지
않았고, 공유할 때 기록 파일 하나를 더하면 되도록 간단해야 한다.

Decided (technical, session): 공유는 글을 올린 뒤에 생기는 일이라 글 파일의 헤더가 아니라 링크·패치처럼 별도의 기록이다.
공유 표 `content/shares.jsonl`의 한 줄이 공유 하나다: `{"post": <글 id>, "where": <곳>, "url": <주소>, "at": <UTC 시각>}`
(표로 옮김 `source:tb-04`). `where`는 빌드가 아는 곳 중 하나다 — 처음은 `x`, `threads`,
`linkedin`이었고(뒤에 `substack`), 곳을 늘리는 일은 빌드에 이름과 아이콘을 더하는 사이트 작업이다. `url`은 `https://`로 시작한다. JSON 객체가
아니거나, 키 집합이 위와 다르거나, `post`가 없는 글이거나, `where`가 모르는 곳이거나, `url`·`at`의 형식이 틀리면 빌드 오류이고
오류 줄은 그 공유의 줄을 가리킨다. 한 글에 공유가 여럿이면 `at` 순(같으면 줄 순서)으로 배지를 단다. 배지는 사이트 안에 둔 아이콘 파일이고(아래 결정) 외부에서 가져오지 않으며, 곳의 이름을 `aria-label`로 가진다. 공유가 없는
글에는 배지 자리가 없다.

Decided (owner, `source:ic-01`, `source:ic-03`; 제안 `source:ic-02`): 아이콘의 모양은 사이트 전체에서 한 번만 정의한다 —
배지가 몇 개든 페이지에 아이콘 모양(`<path>` 등)이 되풀이되지 않는다.

Decided (owner, `source:bd-01`, `source:bd-03`; 제안 `source:bd-02`): 배지의 아이콘은 직접 그린 모양이 아니라 각 곳이 브랜드
자료로 배포하는 공식 로고 파일이다. 소유자가 받은 공식 파일을 `public/assets/brands/<곳>.<svg|png>`에 두고 — X `x.svg`,
Threads `threads.svg`, LinkedIn `linkedin.png`(공식 묶음에 벡터 파일이 없다), Substack `substack.png`, Bluesky `bluesky.svg`(공식 미디어 키트의 검정 나비) — 빌드는 그 파일을 바이트
그대로 `docs/assets/brands/`에 복사한다. 배지는 그 파일을 가리키는 `<img>`이고(`src`는 페이지 기준 상대 경로
`<root>assets/brands/<곳>.<확장자>`, `alt=""`, 곳의 이름은 전처럼 링크의 `aria-label`), 모양·비율을 바꾸지 않는다. 각 곳의
브랜드 규칙을 따른다: X·Threads·LinkedIn·Bluesky는 공식 검정 변형이고(X의 공식 SVG는 흰색으로 배포되어 채움 색만 공식 변형인 검정
`#000`으로 바꿔 두었다), Substack은 색을 바꾸지 말라는 규칙에 따라 주황색 원본이다. 배지 사이에는 로고 주변 여백을 둔다.
곳은 이제 `x`, `threads`, `linkedin`, `substack`, `bluesky`이다(Bluesky는 소유자가 공식 파일을 준 뒤 더함). 이 결정은 위의 흑백 SVG 배지와 `icons.svg` 방식을 대신한다.

Decided (technical, delegated — 구현자 brand-build의 결정, 세션이 브라우저에서 네 배지를 나란히 보고 받아들임): 배지 이미지의
높이는 1.1rem이고, `substack.png`는 공식 파일 가장자리의 여백이 넓어 파일을 고치지 않고 표시 높이를 1.8rem으로 키워 로고
부분이 다른 배지와 비슷한 크기로 보이게 한다.

## Q-tag — 태그와 태그 클라우드

Concept: `tag`.

Decided (owner, `source:tg-01`, `source:tb-01`; 제안 `source:tb-03`): 태그를 달고 떼는 일은 시각과 이유가 있는 사건이다. 태그 표
`content/tags.jsonl`의 한 줄이 사건 하나다: `{"post": <글 id>, "tag": <태그 이름>, "action": "added" | "removed", "at": <UTC
시각>, "why": <문자열>}`. 태그 목록을 손으로 관리하지 않는다 — 글에 지금 달린 태그, 태그마다의 글, 태그 클라우드는 빌드가 표에서
계산한다. 글·태그 짝의 마지막 사건이 `added`면 그 태그가 지금 달려 있다.

Decided (technical, session): 한 글·태그 짝의 첫 사건은 `added`이고, 사건은 `added`와 `removed`가 번갈아 온다(떼었다 다시 달 수
있다). 사건의 시각은 줄 순서대로 내려가지 않는다. 태그 이름은 1–40자이고, 앞뒤 공백이 없으며, `/`·`\`·줄바꿈을 담지 않고
`.`이나 `..`이 아니다. 키 집합이 다르거나, `post`가 없는 글이거나, 이름·사건 순서·시각이 규칙에 어긋나면 빌드 오류이고 오류 줄은
그 표의 줄을 가리킨다.

Decided (owner, `source:tg-03`, `source:tg-04`): 태그 클라우드는 피드 옆에 둔다 — 넓은 화면에서는 피드 오른쪽, 좁은 화면(모바일)에서는
피드 아래. 메뉴에 태그 탭은 두지 않는다. 태그를 누르면 그 태그가 달린 글만 모은 페이지로 간다. 글 페이지의 태그도 그 페이지로
가는 링크다.

Decided (technical, session): 피드 페이지의 클라우드는 `<aside class="tag-cloud">`이고, 지금 달린 태그를 이름 순으로 한 번씩
보여준다. 태그마다 달린 글 수를 함께 적고, 글이 많을수록 글씨가 크다(`0.9rem`–`1.6rem`). 달린 태그가 하나도 없으면 클라우드가
없다. 태그 페이지는 `docs/tags/<태그>/index.html`(주소 `/tags/<태그>/`, 링크에서는 퍼센트 인코딩)이고 제목은 "태그: <태그>"다.
그 태그가 지금 달린 글을 피드와 같은 상자로 최신순으로 보여주고, 상자마다 그 태그를 단 이유(마지막 `added`의 `why`)와 시각을
적는다. 글 페이지는 지금 달린 태그를 이름 순으로 태그 페이지 링크로 보여준다.
