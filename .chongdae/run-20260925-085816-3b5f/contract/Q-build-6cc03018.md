## Q-build — 생성기와 출력

Concept: `site-build`.

`python3 build.py`는 `content/`를 읽고 `docs/`를 통째로 다시 만든다. 결과는 `docs/index.html`(피드), 글마다
`docs/p/<id>/index.html`, `docs/about/index.html`(소개, Q-about), `docs/assets/`(CSS, 자바스크립트, 공유 곳의 로고 `brands/`), `docs/images/`(`content/images/`의 복사본), 빈 파일
`docs/.nojekyll`이다. 같은 입력이면 출력이 바이트 단위로 같다(빌드 시각 같은 값은 넣지 않는다). 표준 라이브러리만 쓴다.
외부에서 가져오는 스크립트·글꼴·스타일은 없다.

입력이 잘못되면 빌드는 stderr에 잘못된 파일의 경로를 포함한 한 줄을 쓰고 종료 코드 1로 끝나며, `docs/`는 빌드 전 그대로
남는다(새 출력은 임시 디렉터리에 만든 뒤 교체한다). 잘못된 입력은 이 문서의 각 절이 "빌드 오류"라고 적은 경우다.

Decided (technical, delegated): `build.py`는 저장소 루트에 있고, 실행한 현재 작업 디렉터리의 `content/`를 읽어 같은 디렉터리의
`docs/`에 쓴다. 테스트는 `build.py`를 테스트 파일 위치 기준의 경로로 찾아 `sys.executable`로 실행하며, 작업 디렉터리를 새 임시
디렉터리로 두어 테스트마다 자기 `content/`와 `docs/`를 갖는다. 테스트는 `tests/`에 있고 `python3 -m unittest discover -s tests`로
돈다.

Decided (owner, `source:rf-01`, `source:rf-03`; 제안 `source:rf-02`): 생성기는 동작을 바꾸지 않고 역할별 모듈로 나눈다. `build.py`는
진입점으로만 남고(실행 명령은 그대로 `python3 build.py`), 나머지는 저장소 루트의 패키지 `sitegen/`에 있다 — 기록 표와 글
파싱(`records`), 마크다운 렌더(`markdown`), 패치 적용과 패치 보기(`patches`), 페이지 렌더(`pages`: 피드·글·태그·소개와 공통 틀),
출력 쓰기와 빌드 순서(`output`). CSS와 자바스크립트는 파이썬 문자열이 아니라 `sitegen/assets/`의 실제 파일이고, 빌드가 그대로
`docs/assets/`로 복사한다. 테스트가 되풀이하던 도우미(임시 사이트 만들기, 빌드 실행, 출력 읽기)는 `tests/support.py` 한 곳에
있고 각 테스트 파일은 그것을 가져다 쓴다; 테스트가 확인하는 계약은 바뀌지 않는다. 리팩터링의 판정은 두 가지다: 모든 테스트가
통과하고, 저장소의 `content/`로 빌드한 `docs/`가 리팩터링 전과 바이트 단위로 같다.

Decided (technical, delegated): 패키지 이름은 제안의 `site/`가 아니라 `sitegen/`이다 — `site`는 파이썬 표준 라이브러리 모듈
이름이라 가려질 수 있다.

Decided (owner, `source:about-06`, `source:about-08`): 주소는 폴더 방식이다 — 첫 화면 `/`, 글 `/p/<id>/`, 소개 `/about/`.
사이트가 만드는 링크는 파일 이름(`index.html`, `.html`)을 쓰지 않고 폴더로 건다: 피드로는 `./`(글 페이지에서 `../../`,
소개에서 `../`), 글로는 `p/<id>/`, 소개로는 `about/`. 공통 파일과 이미지도 각 페이지 위치 기준의 상대 경로다. 첫 화면은 피드이고,
모든 페이지 위쪽 메뉴에 "피드"와 "소개" 링크가 항상 있다.

Decided (technical, delegated): 저장소 루트의 기존 `index.html`은 `docs/`로 옮겨지지 않는다 — 피드가 새 첫 화면이다. Pages의
서비스 위치를 main의 `/docs`로 바꾸는 것은 푸시할 때 소유자가 한다.
