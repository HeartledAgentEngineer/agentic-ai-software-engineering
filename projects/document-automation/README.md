# Document automation

A small, local Node.js pipeline for application documents. A CV is kept as **data** (one JSON file), checked
against simple rules, rendered to HTML with every value escaped, and printed to an A4 PDF. A second script merges
cover letter, CV and certificates into one PDF. Everything runs on my own machine; the repository only holds an
invented sample person ("Alex Beispiel").

**Stack:** Node.js 20+ · Puppeteer (headless Chrome) · `pdf-lib` · `node:test`

## How it works

```
data/beispiel_person.json ─▶ src/cv_model.js   (validate: required fields, YYYY-MM dates, end after start)
                          ─▶ src/render_html.js (HTML template, every value escaped)
                          ─▶ build.js           ─▶ output/lebenslauf.html ─▶ output/lebenslauf.pdf
certificate PDFs          ─▶ merge_pdfs.js      ─▶ one application PDF
```

- `build.js` is the command line. Exit codes are part of the contract: **0** = written, **1** = the data is
  invalid (every problem is listed), **2** = file not readable or the PDF step failed.
- Puppeteer is loaded only for the PDF step. Validation and rendering — and their tests — need no browser.
- `merge_pdfs.js` copies all pages in the usual German order (cover letter → CV → degree → references →
  certificates) and stops with a clear message if a file is missing.

## Decisions

- **Data, not documents.** The CV is one JSON file; layout lives in the template. Changing a job entry never means
  re-formatting a document by hand.
- **Validate before rendering.** Wrong data fails early with a readable list, instead of producing a broken PDF.
- **Escape everything.** Values go through one `maskiere()` function, so text from the data file can never
  become markup.
- **Local scripts instead of a cloud workflow:** no running costs and no applicant data at a third party.

## Run it

```powershell
npm test                 # 11 tests, no install needed
npm run build:html       # HTML only, no browser needed
npm install              # once, for the PDF step
npm run build            # HTML + A4 PDF into output/
npm run merge            # needs the certificate PDFs, see merge_pdfs.js
```

## Tests

`test/cv.test.js` (Node's built-in test runner) covers the sample data, every validation rule, HTML escaping, date
formatting, the exit codes of `build.js`, and the error paths of `merge_pdfs.js`. The PDF itself is checked by eye — a visual test would need a browser
in CI and buys little for a one-page layout.

← [Back to overview](../../README.md)
