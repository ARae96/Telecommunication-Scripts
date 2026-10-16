# Genesys Architect Flow Export and Caller Map

This folder holds the tooling that maps out the complete set of options a caller
can run into when they phone the business. Starting from one or more Architect
flows, it walks the whole dependency tree, downloads each flow's configuration,
and builds a caller routing map you can open in Lucidchart.

## Scripts

### `Architect_Flow_Export_And_Map.py` (main script)

This is the script to run. From a list of starting flow IDs it:

1. Walks the dependency tree of each starting flow and gathers every flow and
   operating schedule across all of them, with no duplicates even when two
   trees share an item.
2. Downloads each flow's full published configuration.
3. Writes three outputs, all stamped with the same run time so they pair up.

### `Architect_Flow_Tree_Review.py` (earlier, review-list-only script)

The earlier version that produced only the Excel review list (and, in one
version, a paste-into-Dev-Center JSON request). The main script above now does
everything this one did and more. It is kept for reference; you do not need it
for the normal workflow.

## What a run produces

All three outputs land in this folder and share one timestamp, for example a run
at `20261016_150650` writes:

- `Architect_Export_Review_<timestamp>.xlsx`
  A review list of every flow and operating schedule found. Each row shows the
  item type, name, ID, and a link that opens the item in the Genesys web app.

- `Architect_Flow_Export_<timestamp>/`
  A folder with one JSON file per flow, each holding that flow's full published
  configuration, named `<flow name>_<flow id>.json`.

- `Architect_Flowchart_<timestamp>.mmd`
  A Mermaid flowchart of how the flows route callers to each other. This is the
  file you import into Lucidchart (see below).

## How to run it

From the workspace root (one folder up from here), using the project's virtual
environment so the dependencies are available:

```
.venv/bin/python "Genesys Architect/Architect_Flow_Export_And_Map.py"
```

Before running, set the starting flow IDs near the top of the script in the
`STARTING_FLOW_IDS` list. List as many as you like, one per line, each in
quotes. The run signs in to Genesys using the credentials in the workspace
`.env` file (`GENESYS_CLOUD_CLIENT_ID`, `GENESYS_CLOUD_CLIENT_SECRET`,
`GENESYS_CLOUD_REGION`).

## A note on the file format (configuration JSON, not YAML)

The downloaded files hold each flow's configuration as JSON, read straight from
Genesys. This is not the same as the Architect "YAML export" you get from the
Architect UI. The YAML export is built by a background job that must be tied to
a real user sign-in, which the client-id-and-secret sign-in this script uses
does not have. The configuration JSON holds the full flow definition and can be
read without a user, so it is what we can pull automatically. Use it to review,
compare, or archive flow logic. If you need the re-importable YAML for a flow,
export that one by hand from the Architect UI using the review list.

## How to read the flowchart

The chart shows one box per flow and one arrow per routing step:

- A solid arrow with a number is a menu choice, labeled with the key the caller
  presses and the choice name (for example `3: Financial Services Submenu`).
- A dotted arrow is a transfer that happens by logic rather than a key press.
  Where the script can read the decision behind it, the arrow is labeled with
  the branch and the condition (for example
  `No: Task.LexSSN == Task.SalesforceSSN`). Where there is no single readable
  decision, the arrow is labeled `auto`.
- A red box is an outside phone number the caller is transferred to, shown with
  the number.
- A box marked `(outside set)` is a transfer target that was not in the walked
  trees (for example a queue, a group, or a flow outside the starting list).

Box colors group the flows by role: blue rounded boxes are entry points (where a
call can start), light-blue boxes are regular flows, red boxes are external
phone numbers, and orange boxes are outside-the-set targets.

### Honest limits of the chart

- Menu digits, choice names, and phone numbers are read straight from the
  configuration, so those are exact.
- The decision conditions are the raw Genesys expressions, which are accurate
  but technical. You may want to reword a few in plain English after import.
- Some logic transfers stay labeled `auto` because the routing chains through
  more than one decision, which the script does not try to untangle. Those
  arrows show where a caller goes, not the exact trigger.

## Importing into Lucidchart

Lucidchart reads Mermaid flowchart syntax directly. To bring the chart in:

1. Open the `Architect_Flowchart_<timestamp>.mmd` file and copy all of its text.
2. In Lucidchart, start a new document, then use the Mermaid import option
   (Insert menu, or the "Diagram as code" / Mermaid panel) and paste the text.
3. Lucidchart renders an editable diagram. From there you can rearrange boxes,
   reword the technical condition labels, and group the trees as you like.

The flowchart is plain Mermaid with simple `style` color lines, which import
more reliably than other styling. If a given Lucidchart version does not apply
the colors, the diagram still imports correctly; you would just re-apply colors
inside Lucidchart.
