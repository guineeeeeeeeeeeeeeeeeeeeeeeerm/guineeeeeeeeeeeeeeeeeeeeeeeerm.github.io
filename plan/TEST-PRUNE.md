# 테스트 줄이기 목록 (승인: `source:tf-05`, 목록 제시: `source:tf-04`)

Q-build "테스트 시간" 4번에 따라 만든 목록이고, 소유자가 전부(A~E) 승인했다. 계획서가 따로 정한 규칙을 지키는 유일한 테스트는
넣지 않았다(아래 "남기는 것"). 빌드 수는 이 목록을 만들 때(테스트 134개, 빌드 222번) 기준이다.

## A. 중복 삭제

| 테스트 | 덮는 테스트 | 처리 |
|---|---|---|
| test_s1::test_Q_post_written_is_required | test_s1::test_Q_build_bad_input_is_atomic… (같은 입력, 더 강한 확인) | 삭제 |
| test_s1::test_Q_build_same_input_is_byte_identical_on_second_build | test_frame::test_Q_build_same_content_twice_produces_byte_identical_docs | 삭제. frame 준비물에 그림 하나를 더함 |
| test_s1::test_Q_post_images_only_body_is_valid_and_renders_image | test_s1::test_Q_feed_titleless_image_first_paragraph…, test_image_zoom::test_Q_post_image_on_a_post_page… | 삭제 |
| test_s1::test_Q_post_page_shows_title_and_written_but_no_type_name | test_s1::test_Q_post_short_title_is_forbidden…, test_s1::test_Q_ui_sets_korean… | 삭제 |
| test_s1::test_Q_feed_short_shows_full_applied_body_medium_long_show_title_and_time | test_feed_layout의 세 테스트, test_s1::test_Q_time_uses_utc…, test_s1::test_Q_ui… | 삭제 |
| test_s1::test_Q_feed_every_item_links_to_its_post_page_and_has_applied_content | test_feed_layout::test_the_whole_box_links_to_the_post…, ::test_a_short_post_has_no_title_line… | 삭제 |
| test_frame::test_Q_build_invalid_input_exits_one_names_the_file_and_preserves_existing_docs | test_about::test_a_missing_about_md_is_a_build_error, test_s1::…atomic… | 삭제 |
| test_about::test_every_page_has_the_feed_and_about_menu_as_folder_links | test_frame::test_Q_build_every_page_has_the_same_frame_and_ordered_feed_about_nav | 삭제 |
| test_about::test_Q_post_external_links_are_links_on_about_and_post_pages | test_about::test_about_md_becomes_the_about_page…, test_external_links::test_Q_post_http_and_https_links_render_in_every_post_type | 삭제 |
| test_about::test_the_readme_shows_how_to_write_the_about_page_and_its_example_builds | test_readme::test_Q_readme_fenced_post_link_and_patch_examples_build_and_render | test_readme에 합침: 절 제목 "소개"와 `docs/about/index.html` 확인만 옮김 |
| test_images::test_a_width_after_the_bar_sets_the_display_width_and_leaves_the_alt | test_image_zoom::test_Q_post_image_on_a_post_page_is_wrapped_and_keeps_the_original_and_width | 삭제 |
| test_images::test_without_a_width_the_image_has_no_width_attribute | 같은 image_zoom 테스트 | 삭제. width가 없다는 확인을 그 테스트에 명시 |
| test_markdown::test_Q_post_paragraph_and_quote_line_breaks_render_as_br_with_extended_markdown | test_linebreaks의 두 테스트, test_markdown::test_Q_post_commonmark_blocks… | 삭제 |
| test_shares::test_Q_share_the_first_places_are_x_threads_and_linkedin_in_share_time_order | test_shares::test_Q_share_badges_use_icon_paths_relative_to_each_page | aria-label 순서 확인을 icon_paths로 옮기고 삭제 |
| test_s2::test_Q_link_anchor_missing_or_repeated… · ::test_Q_link_unknown_from_or_to… 의 정상 대조군 빌드 | test_s2::test_Q_link_rows_and_event_rules…의 대조군 | 대조군 두 개 삭제 |
| test_s3::test_Q_patch_anchor_must_occur_exactly_once…의 첫 정상 빌드 | test_s3::test_Q_patch_file_shape_and_validation…의 첫 대조군 | 대조군 삭제 |

## B. 바뀐 결정 확인

| 테스트 | 처리 |
|---|---|
| test_shares::test_Q_share_badge_markup_has_no_repeated_path_shape (옛 `icons.svg` 결정) | 삭제 |
| test_shares::test_Q_share_Q_build_icons_svg_defines_each_known_share_symbol_once | 이름만 바꿈(예: …brand_logos_are_copied_byte_for_byte) |
| test_about::test_the_about_page_looks_like_a_post_page 의 `#0e0e10`, `text-align: center` 부재 단언 | 두 단언 삭제(`.about` 부재는 유지) |

## C. 오류 사례 표 줄이기 (대표 사례만 남김)

| 테스트 | 지금 → 남길 것 |
|---|---|
| test_s2::test_Q_link_rows_and_event_rules… | missing-link/from/to/at/why 삭제. missing-anchor, extra-key와 나머지는 유지 |
| test_shares::test_Q_share_a_bad_share_row… | missing-url/where/at 삭제. missing-post는 유지 |
| test_ids::test_a_name_that_is_not_a_moment… · ::test_a_name_for_another_moment… | 8가지 → `hello.md`, `20260924-0759.md`, `20260924-075922.md` 세 가지 |
| test_about::test_an_external_link_must_be_http_or_https | 4가지 → `javascript:alert(1)` 하나 |
| test_external_links::test_Q_post_non_http_external_address… | 4가지 → `javascript:alert(1)`, `""` 두 가지 |
| test_markdown::test_Q_post_non_http_reference_and_angle_links… | 4가지 → 참조 `mailto` 하나, 꺾쇠 `javascript` 하나 |
| test_external_links::test_Q_post_untitled_medium_and_long_feed_titles… | 2가지 → medium 하나 |
| test_tags::test_bad_rows… 의 태그 이름 `"AI "` | 삭제(`" AI"`가 같은 검사를 덮음) |

## D. 부수 마크업 느슨하게 (빌드 수는 그대로)

| 테스트 | 처리 |
|---|---|
| test_image_zoom의 글·소개·패치 그림 테스트 | `<img …>` 문자열 전체 대신 href, src, alt, width를 따로 확인 |
| test_image_zoom의 script 테스트와 피드 그림 테스트 | src와 defer를 따로 확인. 피드는 image-zoom이 없다는 것만 확인 |
| test_feed_layout::test_the_whole_box_links_to_the_post_by_one_empty_covering_link | CSS 단언 두 개 삭제(href와 aria-label은 유지) |
| test_tags::test_the_cloud_sits_beside_the_feed… | 감싸는 요소 정규식과 grid 단언을 덜어냄. `<aside class="tag-cloud">`, 글 수, 글씨 크기, 64rem은 유지 |
| test_shares::test_Q_share_a_share_is_a_badge… | `.share-badge` CSS 단언 두 개 삭제 |
| test_about::test_the_about_page_looks_like_a_post_page | `<body>` class 단언 삭제 |
| test_s3의 토글·이력·삭제 표시 테스트 | 자산 안의 구현 이름 정규식을 덜어냄. 버튼, `aria-pressed="false"`, 이력 값은 유지 |

## E. 빌드 나눠 쓰기 (클래스 단위 준비, 확인하는 계약은 그대로)

- test_feed_layout: 8개 테스트가 같은 `SITE`를 씀
- test_frame: 준비물이 같은 세 테스트
- test_about: 두 테스트
- test_shares: 준비물이 같은 두 쌍
- test_s1: `{ID: post_text()}`를 쓰는 두 테스트
- test_linebreaks: 두 테스트
- test_image_zoom: 두 테스트
- 그 밖에 같은 입력을 여러 번 빌드하는 곳이 보이면 같은 방식으로 나눠 씀

## 남기는 것 (겹쳐 보이지만 유일한 규칙 확인)

- test_s1::test_Q_post_tags_header_is_a_build_error
- test_s1::test_Q_ui_sets_korean_document_language_and_shows_no_type_names
- test_s1::test_Q_post_markdown_subset_renders_and_html_is_shown_as_text
- test_s3의 패치 오류 10개와 test_markdown의 문법 기호 4개
