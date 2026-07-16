#set document(
  title: {{DOCUMENT_TITLE}},
  author: "Deep Research Agent",
)

#set page(
  paper: "a4",
  margin: (x: 22mm, top: 20mm, bottom: 20mm),
  footer: context [
    #set text(size: 8.5pt, fill: rgb("#697386"))
    #line(length: 100%, stroke: 0.5pt + rgb("#D9DDE3"))
    #v(4pt)
    #grid(
      columns: (1fr, auto),
      [Deep Research Agent],
      [#counter(page).display("1")],
    )
  ],
)

#set text(
  font: (
    "Noto Sans CJK SC",
    "Noto Sans SC",
    "Microsoft YaHei",
    "SimSun",
    "Arial",
  ),
  lang: "zh",
  size: 10.5pt,
  fill: rgb("#18212F"),
)
#set par(justify: true, leading: 0.72em, spacing: 0.9em)
#set heading(numbering: none)
#show heading.where(level: 1): set text(size: 21pt, weight: "bold")
#show heading.where(level: 2): set text(size: 16pt, weight: "bold")
#show heading.where(level: 3): set text(size: 13pt, weight: "bold")
#show link: set text(fill: rgb("#1769AA"))

{{DOCUMENT_CONTENT}}
