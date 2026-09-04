"""Guards CSV exports against spreadsheet formula injection.

Proper CSV quoting/escaping (handled by the stdlib csv module already)
protects the *file format* - it has nothing to do with protecting
against a spreadsheet application *interpreting* a cell's content as a
live formula once the file is opened. A cell value starting with =, +,
-, or @ can be read as a formula by Excel, LibreOffice, Google Sheets,
etc. - e.g. a beer or brewery name of =HYPERLINK("https://evil.example",
"click") would render as a clickable link pointing wherever an attacker
chose, to anyone who opens an exported CSV in a spreadsheet app. This
matters here specifically because beer/brewery names (and other
free-text fields) are user-controlled and can end up in an admin's
catalog export or a user's own cellar export.

The standard mitigation is to prepend an apostrophe when a value starts
with one of those characters: every mainstream spreadsheet application
treats a leading apostrophe as "treat this cell as plain text", and the
apostrophe itself is invisible in the CSV file and to any non-
spreadsheet consumer of it.
"""

_FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@")


def csv_safe(value):
    if isinstance(value, str) and value[:1] in _FORMULA_TRIGGER_CHARS:
        return "'" + value
    return value
