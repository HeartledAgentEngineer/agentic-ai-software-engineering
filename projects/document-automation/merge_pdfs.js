// merge_pdfs.js
// Führt das Anschreiben, den Lebenslauf und die Zeugnisse in einem einzigen,
// professionell sortierten PDF-Dokument zusammen.
// Erfordert: npm install pdf-lib
'use strict';

const fs = require('fs');
const path = require('path');

const dir = __dirname;
const outputDir = path.join(dir, 'output');

// Professionelle Reihenfolge für deutsche Bewerbungsunterlagen:
// 1. Anschreiben
// 2. Lebenslauf (CV, erzeugt von build.js)
// 3. Höchster Bildungsabschluss (Bachelor-Zeugnis)
// 4. Arbeitszeugnisse
// 5. Fortbildungen / Zertifikate
const defaultFiles = [
    path.join(outputDir, 'muster_anschreiben.pdf'),
    path.join(outputDir, 'lebenslauf.pdf'),
    path.join(dir, 'muster_bachelorzeugnis.pdf'),
    path.join(dir, 'muster_arbeitszeugnis.pdf'),
    path.join(dir, 'muster_zertifikat.pdf')
];

const defaultOutFile = path.join(outputDir, 'muster_bewerbungsmappe.pdf');

async function mergePdfs(files = defaultFiles, outFile = defaultOutFile, pdfLib = null) {
    try {
        for (const file of files) {
            if (!fs.existsSync(file)) {
                console.error(`Datei nicht gefunden: ${file}`);
                console.error('Bitte stelle sicher, dass du zuerst "node build.js" ausgeführt hast und die Eingabe-PDFs existieren.');
                return 1;
            }
        }

        const lib = pdfLib || require('pdf-lib');
        const { PDFDocument } = lib;

        console.log('Starte das Zusammenfügen der PDFs...');
        const mergedPdf = await PDFDocument.create();

        for (const file of files) {
            console.log(`Lese und kopiere Seiten aus: ${path.basename(file)}`);
            const pdfBytes = fs.readFileSync(file);
            const pdfDoc = await PDFDocument.load(pdfBytes);
            const copiedPages = await mergedPdf.copyPages(pdfDoc, pdfDoc.getPageIndices());
            copiedPages.forEach((page) => mergedPdf.addPage(page));
        }

        const mergedPdfBytes = await mergedPdf.save();
        fs.mkdirSync(path.dirname(outFile), { recursive: true });
        fs.writeFileSync(outFile, mergedPdfBytes);
        console.log('\n=========================================');
        console.log('ERFOLG: Alle Dokumente zusammengefügt!');
        console.log('Mappe erstellt:', outFile);
        console.log('=========================================');
        return 0;
    } catch (err) {
        console.error('Fehler beim Zusammenfügen der PDFs:', err);
        return 1;
    }
}

if (require.main === module) {
    mergePdfs().then((code) => process.exit(code));
}

module.exports = { mergePdfs, defaultFiles, defaultOutFile };
