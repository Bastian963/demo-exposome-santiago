// Minimal RFC 4180 CSV, both directions, with no dependency.
//
// The app has no CSV parser and adding one for this would pull a package into a
// bundle that currently ships none. Pasted addresses contain commas and
// accents, so a naive split(",") corrupts exactly the input this feature is for.

// Parses quoted fields, escaped quotes (""), embedded newlines, CRLF and a BOM.
export function parseCSV(text) {
  const input = String(text ?? "").replace(/^﻿/, "");
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  let started = false;

  for (let i = 0; i < input.length; i++) {
    const char = input[i];

    if (quoted) {
      if (char === '"') {
        if (input[i + 1] === '"') {
          field += '"';
          i++;
        } else {
          quoted = false;
        }
      } else {
        field += char;
      }
      continue;
    }

    if (char === '"' && field === "") {
      quoted = true;
      started = true;
      continue;
    }
    if (char === ",") {
      row.push(field);
      field = "";
      started = true;
      continue;
    }
    if (char === "\r") continue;
    if (char === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
      started = false;
      continue;
    }
    field += char;
    started = true;
  }
  if (started || field !== "" || row.length) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

// Returns objects keyed by the header row.
export function parseCSVObjects(text) {
  const rows = parseCSV(text);
  if (!rows.length) return [];
  const header = rows[0].map((name) => name.trim());
  return rows.slice(1)
    .filter((row) => row.some((value) => String(value).trim() !== ""))
    .map((row) => {
      const record = {};
      header.forEach((name, index) => {
        record[name] = row[index] ?? "";
      });
      return record;
    });
}

function escapeField(value) {
  if (value === null || value === undefined) return "";
  const text = String(value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function serializeCSV(records, columns = null) {
  const rows = Array.isArray(records) ? records : [];
  const header = columns || Array.from(
    rows.reduce((keys, record) => {
      Object.keys(record || {}).forEach((key) => keys.add(key));
      return keys;
    }, new Set()),
  );
  const lines = [header.map(escapeField).join(",")];
  for (const record of rows) {
    lines.push(header.map((key) => escapeField(record?.[key])).join(","));
  }
  return lines.join("\n");
}

// Hands the browser a file without a dependency or a server round trip.
export function downloadText(filename, text, mimeType = "text/csv;charset=utf-8") {
  const blob = new Blob([text], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // Revoking synchronously can cancel the download in some browsers.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
