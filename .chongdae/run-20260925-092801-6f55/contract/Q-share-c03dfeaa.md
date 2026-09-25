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
자료로 배포하는 공식 로고 파일이다. 소유자가 받은 공식 파일을 `sitegen/assets/brands/<곳>.<svg|png>`에 두고 — X `x.svg`,
Threads `threads.svg`, LinkedIn `linkedin.png`(공식 묶음에 벡터 파일이 없다), Substack `substack.png`, Bluesky `bluesky.svg`(공식 미디어 키트의 검정 나비) — 빌드는 그 파일을 바이트
그대로 `docs/assets/brands/`에 복사한다. 배지는 그 파일을 가리키는 `<img>`이고(`src`는 페이지 기준 상대 경로
`<root>assets/brands/<곳>.<확장자>`, `alt=""`, 곳의 이름은 전처럼 링크의 `aria-label`), 모양·비율을 바꾸지 않는다. 각 곳의
브랜드 규칙을 따른다: X·Threads·LinkedIn·Bluesky는 공식 검정 변형이고(X의 공식 SVG는 흰색으로 배포되어 채움 색만 공식 변형인 검정
`#000`으로 바꿔 두었다), Substack은 색을 바꾸지 말라는 규칙에 따라 주황색 원본이다. 배지 사이에는 로고 주변 여백을 둔다.
곳은 이제 `x`, `threads`, `linkedin`, `substack`, `bluesky`이다(Bluesky는 소유자가 공식 파일을 준 뒤 더함). 이 결정은 위의 흑백 SVG 배지와 `icons.svg` 방식을 대신한다.

Decided (technical, delegated — 구현자 brand-build의 결정, 세션이 브라우저에서 네 배지를 나란히 보고 받아들임): 배지 이미지의
높이는 1.1rem이고, `substack.png`는 공식 파일 가장자리의 여백이 넓어 파일을 고치지 않고 표시 높이를 1.8rem으로 키워 로고
부분이 다른 배지와 비슷한 크기로 보이게 한다.
