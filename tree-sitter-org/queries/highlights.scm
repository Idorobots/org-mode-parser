; tree-sitter-org highlight queries
; Basic highlights for Org Mode syntax

; --- Document structure ---
(stars) @markup.heading

; --- Headings ---
(heading
  (stars) @markup.heading
  (todo_keyword) @keyword)

(todo_keyword) @keyword
(priority) @constant

(tags) @tag
(tag) @tag

; --- Sections & Elements ---
(property_drawer) @property
(logbook_drawer) @property
(node_property
  (property_name) @property
  (property_value) @string)

; --- Keywords ---
(special_keyword
  (keyword_key) @keyword) @keyword
(caption_keyword) @keyword
(tblname_keyword) @keyword
(results_keyword) @keyword
(plot_keyword) @keyword

; --- Comments ---
(comment) @comment
(comment_block) @comment

; --- Blocks ---
(src_block
  (language) @string.special) @markup.raw
(example_block) @markup.raw
(export_block) @markup.raw
(verse_block) @markup.quote
(center_block) @markup.quote
(quote_block) @markup.quote
(special_block) @markup.raw

; --- Lists ---
(list_item) @markup.list
(unordered_bullet) @punctuation.special
(checkbox) @constant
(counter_set) @constant

; --- Tables ---
(org_table) @markup.raw
(table_row) @markup.raw
(table_cell) @markup.raw
(table_rule) @punctuation.special
(tblfm_line) @keyword

; --- Objects: Markup ---
(bold) @markup.bold
(italic) @markup.italic
(underline) @markup.underline
(strike_through) @markup.strikethrough
(verbatim
  (verbatim_content) @markup.raw) @markup.raw
(code
  (code_content) @markup.raw) @markup.raw

; --- Objects: Links ---
(regular_link
  (link_path) @markup.link.url) @markup.link
(angle_link
  (link_type) @markup.link.url
  (link_path) @markup.link.url) @markup.link
(plain_link
  (link_type) @markup.link.url
  (link_path) @markup.link.url) @markup.link

; --- Objects: Targets ---
(target
  (target_text) @markup.link.url) @markup.link
(radio_target) @markup.link

; --- Objects: Timestamps ---
(timestamp) @string.special
(ts_year) @number
(ts_month) @number
(ts_day) @number
(ts_dayname) @string.special

; --- Planning ---
(planning) @keyword
(planning_keyword) @keyword

; --- Clock ---
(clock) @keyword

; --- Objects: Footnotes ---
(footnote_reference
  (fn_label) @markup.link.url) @markup.link
(footnote_definition
  (fn_label) @markup.link.url)

; --- Objects: Citations ---
(citation) @markup.link
(citation_body) @markup.link.url

; --- Objects: Export snippets ---
(export_snippet
  (snippet_backend) @keyword) @markup.raw

; --- Objects: Inline source ---
(inline_source_block
  (inline_language) @string.special) @markup.raw

; --- Objects: Line break ---
(line_break) @punctuation.special

; --- Objects: Diary sexp ---
(diary_sexp) @string.special

; --- Horizontal rule ---
(horizontal_rule) @punctuation.special

; --- Fixed width ---
(fixed_width) @markup.raw

; --- Plain text (fallback) ---
(plain_text) @spell

; --- Drawers ---
(drawer
  (drawer_name) @property) @property

; --- Dynamic blocks ---
(dynamic_block
  (dynamic_block_name) @keyword)

; --- Error nodes ---
(ERROR) @error
