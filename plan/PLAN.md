# guin-site — plan

목표: 소유자가 평소에 생각하는 것을 마구잡이로 올리는 개인 사이트. 글(가끔 이미지)을 파일로 쓰고, 표준 라이브러리만 쓰는
Python 생성기가 정적 HTML을 `docs/`에 만든다. GitHub Pages가 `docs/`를 서비스한다. 기획의 근거는 `mangsang/`의 원문과
개념이다: 아래 각 절은 개념 하나 이상의 투영이며, 첫 줄에 그 개념을 적는다.

용어: **글 파일**은 `content/posts/<id>.md`, **링크 파일**은 `content/links/<id>.json`, **패치 파일**은
`content/patches/<id>.json`이다. `<id>`는 영문 소문자·숫자·하이픈(`[a-z0-9-]+`)이다. **빌드**는 `python3 build.py`이다.
**본문**은 글 파일의 헤더 다음 텍스트이고, **적용된 본문**은 그 글의 패치를 모두 적용한 뒤의 본문이다.

## Q-build — 생성기와 출력

Concept: `site-build`.

`python3 build.py`는 `content/`를 읽고 `docs/`를 통째로 다시 만든다. 결과는 `docs/index.html`(피드), 글마다
`docs/p/<id>.html`, `docs/assets/`(CSS, 자바스크립트), `docs/images/`(`content/images/`의 복사본), 빈 파일
`docs/.nojekyll`이다. 같은 입력이면 출력이 바이트 단위로 같다(빌드 시각 같은 값은 넣지 않는다). 표준 라이브러리만 쓴다.
외부에서 가져오는 스크립트·글꼴·스타일은 없다.

입력이 잘못되면 빌드는 stderr에 잘못된 파일의 경로를 포함한 한 줄을 쓰고 종료 코드 1로 끝나며, `docs/`는 빌드 전 그대로
남는다(새 출력은 임시 디렉터리에 만든 뒤 교체한다). 잘못된 입력은 이 문서의 각 절이 "빌드 오류"라고 적은 경우다.

Decided (technical, delegated): `build.py`는 저장소 루트에 있고, 실행한 현재 작업 디렉터리의 `content/`를 읽어 같은 디렉터리의
`docs/`에 쓴다. 테스트는 `build.py`를 테스트 파일 위치 기준의 경로로 찾아 `sys.executable`로 실행하며, 작업 디렉터리를 새 임시
디렉터리로 두어 테스트마다 자기 `content/`와 `docs/`를 갖는다. 테스트는 `tests/`에 있고 `python3 -m unittest discover -s tests`로
돈다.

Decided (technical, delegated): 저장소 루트의 기존 `index.html`은 `docs/`로 옮겨지지 않는다 — 피드가 새 첫 화면이다. Pages의
서비스 위치를 main의 `/docs`로 바꾸는 것은 푸시할 때 소유자가 한다.

## Q-post — 글 하나

Concept: `post`, `post-type`, `tag`.

글 파일은 헤더와 본문으로 이루어진다. 헤더는 파일 첫 줄부터 빈 줄 전까지의 `key: value` 줄들이다.

- `written`: 작성 시각. `YYYY-MM-DDTHH:MM:SSZ` 형식의 UTC. 반드시 있다.
- `type`: `short`(짧은 글), `medium`(중간 글), `long`(긴 글) 중 하나. 반드시 있다. 유형은 쓰기 전에 고르는 것이며,
  빌드는 분량으로 유형을 판단하지 않는다.
- `title`: 제목. `short`에서는 있으면 빌드 오류, `medium`과 `long`에서는 선택.
- `tags`: 쉼표로 구분한 태그 이름. 선택. 앞뒤 공백은 무시하고, 빈 이름은 버린다.

Decided after quibble (s1-tests, technical, delegated): 키와 값의 앞뒤 공백은 무시하고, 키는 대소문자를 구분한다. 콜론이 없는
헤더 줄과 같은 키가 두 번 나오는 헤더는 빌드 오류다.

그 밖의 키, 형식이 틀린 `written`, 목록에 없는 `type`, 두 글이 같은 `<id>`(파일 이름)인 경우는 빌드 오류다. 이미지만 있는
글은 본문이 이미지 한 줄인 글이다.

Decided (owner, `source:plan-11`): 본문이 빈 글은 빌드 오류다.

본문은 Markdown의 부분집합이다: 빈 줄로 나뉜 문단, `#`/`##`/`###` 제목, `- ` 목록, `> ` 인용, `**굵게**`, `*기울임*`,
`` `코드` ``, 이미지 `![설명](images/파일)`. 이미지 경로가 `content/images/`에 없으면 빌드 오류다. 본문의 HTML은 글자로
보인다(태그로 해석되지 않는다).

글 페이지 `docs/p/<id>.html`은 제목(있으면), 작성 시각, 태그, 본문을 보여준다.

Decided (owner, `source:plan-11`): 글 페이지와 피드 항목에 유형 이름(짧은 글/중간 글/긴 글)을 작게 표시한다. 태그는 글
페이지에 글자로만 표시하고, 태그별 목록 페이지는 아직 만들지 않는다.

## Q-feed — 첫 화면

Concept: `feed`.

`docs/index.html`은 모든 글을 작성 시각의 최신순으로 한 줄에 보여준다(유형별로 나누지 않는다 — 항목마다 유형 이름이 붙는 것은 Q-post대로다. 같은
시각이면 `<id>` 순). 짧은
글은 본문 전체를 보여주고, 중간·긴 글은 제목과 시각을 보여준다. Decided (owner, `source:plan-11`): 제목이 없는 중간·긴
글은 제목 자리에 본문 첫 문단의 앞 80자(잘렸으면 `…`)를 보여준다. Decided after quibble (s1-tests, technical, delegated): 80자는 적용된 본문의 첫 문단을 HTML로 만든 뒤의 화면 글자(서식
기호와 태그를 뺀 글자)에서 유니코드 문자 단위로 센다. 이미지만 있는 첫 문단은 이미지 설명(alt)을 글자로 쓴다. 모든 항목은
그 글의 페이지로 가는 링크를 가진다. 피드의 본문은 적용된 본문이다.

Dismissed after quibble (s1-tests): "checks가 비어 있다"는 다섯 건 — 트집 작업은 계약 테스트를 쓰는 작업이라 그 테스트가 검사이고,
`s1-build`가 `python3 -m unittest discover -s tests`로 돌린다.

## Q-time — 시각 표시

Concept: `local-time`.

화면의 모든 시각은 `<time datetime="YYYY-MM-DDTHH:MM:SSZ">` 요소로 나오며, 요소의 글자는 UTC로
`YYYY-MM-DD HH:MM UTC`다. 페이지의 자바스크립트가 이를 독자 브라우저의 시간대로 바꿔 `YYYY-MM-DD HH:MM`로 보여주고, 요소의
`title`에 UTC 표기를 남긴다. 자바스크립트가 없으면 UTC 글자가 그대로 보인다.

Decided after the verifier (s1-build-4, technical, delegated): 현지 시각으로 바꾼 연도가 0001–9999 밖이면(예: UTC+14에서
`9999-12-31T23:59:59Z`) 바꾸지 않고 UTC 글자와 `title`을 그대로 둔다. 숫자는 항상 ASCII다.

## Q-ui — 화면 언어

Concept: `ui-language`.

메뉴, 버튼, 안내 문구, 유형 이름(짧은 글/중간 글/긴 글) 등 사이트가 만드는 글자는 한국어다. `<html lang="ko">`.

## Q-link — 주석으로 거는 링크

Concept: `link`.

링크 파일: `{"id", "from": <글 id>, "anchor": <문자열>, "to": <글 id>, "events": [<이벤트>...]}`. 이벤트는
`{"at": <UTC 시각>, "action": "created" | "reason-changed" | "removed", "why": <문자열>}`이며, 첫 이벤트는 `created`, 시각은
오름차순이다. 현재 사유는 마지막 `created` 또는 `reason-changed`의 `why`다. 마지막 이벤트가 `removed`면 그 링크는 화면에
나오지 않지만 파일은 남는다(변경 기록은 관리하되 화면에 보이지 않는다).

`anchor`는 `from` 글의 적용된 본문에 그대로 나오는 문자열이며, 정확히 한 번 나와야 한다(없거나 두 번 이상이면 빌드
오류). 글 페이지에서 그 문자열은 `to` 글로 가는 링크가 되고, 바로 뒤에 위첨자 `[n]`이 붙는다. `n`은 그 글 안에서 앵커가
나오는 순서로 1부터 매긴다. 본문 아래 "주석" 목록의 `n`번 항목은 `to` 글의 제목(없으면 첫 문단 앞 80자)과 현재 사유,
링크를 건 시각(`created`의 `at`)을 보여준다. `from`이나 `to`가 없는 글이면 빌드 오류다.

Decided after quibble (s2-tests, technical, delegated): 앵커 글자는 `<a href="<to>.html">…</a>`가 되고 바로 뒤에
`<sup><a href="#fn-<n>">[n]</a></sup>`가 붙는다. "주석" 목록은 `<ol>`이며 `n`번 항목의 `id`는 `fn-<n>`이다. 글 페이지 사이의
링크는 같은 디렉터리(`docs/p/`) 기준의 상대 경로다.

Decided (owner, `source:plan-11`): 받는 쪽 글(`to`)의 페이지 아래에 "이 글을 가리키는 글" 목록을 두고, 각 항목은 `from`
글의 제목(없으면 첫 문단 앞 80자)과 현재 사유를 보여준다.

Decided after quibble (s2-tests, technical, delegated): 이 목록은 링크를 건 시각(`created`의 `at`)의 최신순이고, 같으면 링크
`id` 순이다. 마지막 이벤트가 `removed`인 링크는 넣지 않는다. 가리키는 글이 없으면 목록을 두지 않는다.

Dismissed after quibble (s2-tests): "checks가 비어 있다" — 트집 작업의 테스트가 검사이고 `s2-build`가 돌린다.

## Q-patch — 패치

Concept: `patch`.

패치 파일: `{"id", "post": <글 id>, "at": <UTC 시각>, "why": <문자열>, "op": "replace" | "insert-before" | "insert-after" |
"delete", "anchor": <문자열>, "text": <문자열>}` (`delete`에는 `text`가 없다). 한 글의 패치는 `at` 오름차순(같으면 `id`
순)으로 차례로 적용되고, 각 패치의 `anchor`는 그때까지 적용된 본문에 정확히 한 번 나와야 한다(아니면 빌드 오류). 그래서 앞선
패치가 만든 글에 패치를 붙일 수 있다. `replace`는 앵커를 `text`로 바꾸고, `insert-before`/`insert-after`는 앵커 앞/뒤에
`text`를 넣고, `delete`는 앵커를 지운다. 패치는 한 글 안에서만 작용하며 길이 제한은 없다. 글 파일 자체는 패치로 바뀌지
않는다(원문은 남는다).

Decided after quibble (s3-tests, technical, delegated): 패치 파일은 `content/patches/*.json`이고 파일 하나가 패치 하나다. `id`는
문자열이며 파일 이름(확장자 제외)과 같아야 한다. JSON이 아니거나, 키 집합이 위와 다르거나, `op`가 목록에 없거나, `delete`에
`text`가 있거나 다른 `op`에 없거나, `at`이 `written`과 같은 형식이 아니거나, `post`가 없는 글을 가리키면 빌드 오류이고, 오류
줄은 그 패치 파일의 경로를 포함한다. 같은 `at`의 패치는 `id`의 문자열 순서로 적용한다. 앵커는 패치를 적용하기 전 그 순간의
본문(글 파일의 본문에 앞선 패치를 적용한 것)에서 찾으므로, 다른 글이나 글 경계 밖을 가리킬 수 없다.

Decided (owner, `source:plan-05`): 올린 글을 고치는 일반적인 방법은 패치 파일을 더하는 것이고, 글 파일을 직접 고치는 일은 이
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
