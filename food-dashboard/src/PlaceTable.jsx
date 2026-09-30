import { Fragment, useState, useMemo, useEffect, useRef } from "react";
import { flushSync } from "react-dom";
import { useReactTable, getCoreRowModel, getSortedRowModel, getPaginationRowModel, flexRender } from "@tanstack/react-table";
import { listPrintColumns, listPrintName, listPrintRows, listScope, orderPhrase, saveCsv } from "./lib/format";
import { useAdvanced } from "./useAdvanced";
import { useMeta, useMode } from "./useMeta";
import { passesFilters, sortPlaces, shownPoints, lastVisitStale, flagWindowNote } from "./lib/filters";
import { StaleBadge } from "./PlaceParts";
import { ESCALATION_CAVEAT, ESCALATION_FLAGS, FLAG_LABELS, factTags, typeLabel, visitPhrase, visitShort } from "./lib/inspections";
import { gradeView } from "./lib/grades";
import { markFor, shownBand } from "./lib/marks";
import { bandDefs, bandSummary } from "./lib/bands";
import { searchPlaces } from "./lib/search";
import { fmtDate, fmtShort } from "./lib/dates";
import { gradeContextSentence } from "./lib/framing";
import { describePrints, isStaff, PUBLIC_RECORD_NOTE, USE_NOTE } from "./lib/staff";
import { SITE, STUDENT_NOTE } from "./site";

const PAGE_SIZE = 50;
const DRAWER_HEIGHT = "44vh";
const TOGGLE_HEIGHT = 40;

const factsText = (p) => (p.flags ?? []).map((k) => FLAG_LABELS[k] ?? k).join("; ");

/**
 * In the list, a City address without the city, the state and the ZIP's last four, which every row
 * repeats or which split the line ("1250 J ST, 92101"); the place's own view gives it in full, and an
 * address outside the City keeps its town.
 */
export const listAddress = (a) => String(a ?? "").replace(/,\s*SAN DIEGO,\s*CA\b\s*/i, ", ").replace(/(\d{5})-\d{4}\s*$/, "$1");

/** Where a list's facts sit, for its closing note: the drawer's and the printout's last column. */
export const FACTS_IN_LAST_COLUMN = "The last column is";
/** The staff list's facts, in their last column on a wide screen and under each place's name otherwise. */
export const FACTS_EITHER_PLACE = "The facts (in the last column on a wide screen, or under each place’s name) are";
/** The staff list's facts beside an open place: always under each place's name. */
export const FACTS_UNDER_NAME = "The facts under each place’s name are";

/**
 * The list's closing note on its facts: where they sit (`where`), that they are our reading and of
 * which months, and, when an escalation fact is among `keys`, that meeting one is not a County finding.
 */
export function factsNote(where, keys = []) {
  const esc = keys.some((k) => ESCALATION_FLAGS.includes(k));
  return `${where} ${flagWindowNote(keys).replace(/^Our/, "our")}${esc ? ` ${ESCALATION_CAVEAT}` : ""}`;
}

/**
 * The facts as a line of text (lib/inspections.js factTags), in a few words each, separated by dots:
 * the escalation facts in ink and semibold, then the themes of the majors on one line of their own.
 * Each fact's full wording is given to screen readers and as a tooltip; the place's own view gives
 * every fact and theme in full. Under a place's name (`label`) the facts are marked "Our reading:",
 * as the facts column's heading marks them. `short` (beside an open place, where the Place column is
 * narrow) holds the facts to two lines and the themes to one, so rows stay short; the full wording
 * stays in the tooltips, for screen readers, and in the place's own view.
 */
function FactTags({ flags, label = false, short = false, className = "" }) {
  const t = factTags(flags);
  const items = [...t.record.map((x) => ({ ...x, strong: false })), ...t.escalation.map((x) => ({ ...x, strong: true }))];
  if (!items.length && !t.themes.length) return null;
  const lead = label ? <span className="text-ink-3">Our reading: </span> : null;
  const themes = t.themes.join(", ");
  return (
    <span className={`block text-[12px] leading-snug text-ink-2 ${className}`}>
      {items.length > 0 && (
        <span className={short ? "line-clamp-2" : "block"}>
          {lead}
          {items.map((x, i) => (
            <Fragment key={x.key}>
              {i > 0 && <span aria-hidden="true"> &middot; </span>}
              <span className={x.strong ? "font-semibold text-ink" : undefined}>
                <span aria-hidden="true" title={x.full}>{x.short}</span>
                <span className="sr-only">{x.full}.</span>
              </span>
            </Fragment>
          ))}
        </span>
      )}
      {themes && <span title={`Majors: ${themes}`} className={short ? "line-clamp-1" : "line-clamp-3"}>{items.length ? null : lead}Majors: {themes}</span>}
    </span>
  );
}

/**
 * The columns, all from the index. `bands` mode leads with the band and the points (where the export
 * gives them; the staff list puts both in one column); `record` mode has neither. There is no position
 * column in any mode. The grade is gradeView's, as everywhere. The place's kind sits under its name,
 * with its address; the name's button is the place's name, kind and address only, and carries the
 * place's id and, for the open place, aria-current. A last visit more than a year before the record's
 * end carries a badge; a visit type that is our reading of the County's says so (visitPhrase). In the
 * full-page list (`inline`, the staff site) the last visit and the facts give way on narrower screens,
 * and at every width while a place's panel stands beside the list (`beside`): the facts then sit
 * under the place's name, marked "Our reading:", and so does the badge, so the table never scrolls
 * sideways.
 */
const makeColumns = ({ mode, meta, onSelect, inline = false, beside = false }) => [
  ...(mode === "bands" && inline
    ? [
        {
          id: "band",
          header: "Band, points",
          // Band 1 first, and the most points first within a band, as the site orders the list.
          accessorFn: (f) => (Number(shownBand(f.properties, { mode })) || 99) * 100000 - (shownPoints(f.properties, { mode }) ?? -1),
          meta: { td: "whitespace-nowrap" },
          cell: ({ row }) => {
            const p = row.original.properties;
            const m = markFor(p, { mode });
            const pts = shownPoints(p, { mode });
            return (
              <span className="tnum block">
                {m.label && <span className="block font-semibold" style={{ color: m.text ?? undefined }}>{m.label}</span>}
                {pts != null && <span className="block text-[12px] leading-snug text-ink">{pts} {pts === 1 ? "point" : "points"}</span>}
              </span>
            );
          },
        },
      ]
    : mode === "bands"
    ? [
        {
          id: "band",
          header: "Band",
          accessorFn: (f) => Number(shownBand(f.properties, { mode })) || 99,
          meta: { td: "whitespace-nowrap" },
          cell: ({ row }) => {
            const m = markFor(row.original.properties, { mode });
            return <span className="tnum font-semibold" style={{ color: m.text ?? undefined }}>{m.label ?? ""}</span>;
          },
        },
        {
          id: "points",
          header: "Points",
          accessorFn: (f) => shownPoints(f.properties, { mode }) ?? -1,
          meta: { td: "whitespace-nowrap" },
          cell: ({ row }) => <span className="tnum text-ink">{shownPoints(row.original.properties, { mode }) ?? ""}</span>,
        },
      ]
    : []),
  {
    id: "name",
    header: "Place",
    accessorFn: (f) => f.properties.name,
    meta: { td: "min-w-[12rem]" },
    cell: ({ row, getValue, table }) => {
      const p = row.original.properties;
      const selectedId = table.options.meta?.selectedId;
      const on = selectedId != null && p.facility_id === selectedId;
      return (
        <>
          <button
            type="button"
            data-place-id={p.facility_id}
            aria-current={on ? "true" : undefined}
            onClick={(e) => { e.stopPropagation(); onSelect(row.original); }}
            className="block text-left hover:underline focus:underline"
          >
            <span className="block font-medium text-ink">{getValue()}</span>
            <span className="block text-[12px] leading-snug text-ink-2">{typeLabel(p.facility_type)} &middot; {inline ? listAddress(p.address) : p.address}</span>
          </button>
          {/* Outside the button, so its name stays the place's; a click on them reaches the row. */}
          {inline && <StaleBadge place={p} meta={meta} className={beside ? "mt-1" : "mt-1 lg:hidden"} />}
          {inline && <FactTags flags={p.flags} label short={beside} className={beside ? "mt-1" : "mt-1 xl:hidden"} />}
        </>
      );
    },
  },
  {
    id: "district",
    header: "District",
    accessorFn: (f) => f.properties.council_district ?? 0,
    // As narrow as "D8", so the Place column gets the room.
    meta: { th: "w-px", td: "w-px whitespace-nowrap" },
    cell: ({ getValue }) => <span className="tnum">{getValue() ? `D${getValue()}` : ""}</span>,
  },
  {
    id: "grade",
    header: "Latest grade",
    accessorFn: (f) => f.properties.grade?.date ?? "",
    meta: { td: "min-w-[7rem]" },
    cell: ({ row }) => {
      const g = gradeView(row.original.properties.grade);
      return <span className="tnum font-semibold" style={g.textColor ? { color: g.textColor } : undefined}>{g.graded || g.closedOpen ? g.short : <span className="font-normal text-ink-2">{g.withDate ?? g.text.toLowerCase()}</span>}</span>;
    },
  },
  {
    id: "last",
    header: "Last visit",
    accessorFn: (f) => f.properties.last_visit?.date ?? "",
    meta: {
      th: inline ? (beside ? "hidden" : "hidden lg:table-cell") : "",
      td: inline ? (beside ? "hidden" : "hidden min-w-[8rem] max-w-[11rem] lg:table-cell") : "whitespace-nowrap",
    },
    cell: ({ row }) => {
      const v = row.original.properties.last_visit;
      if (!v) return "";
      const stale = lastVisitStale(row.original.properties, meta) && <StaleBadge className="ml-1.5" />;
      if (!inline) {
        return (
          <span className="tnum">
            {fmtShort(v.date)}, {visitPhrase(v)}
            {stale}
          </span>
        );
      }
      // In the narrow column a visit we read is shortened, still marked; its full words go to screen readers.
      const full = visitPhrase(v);
      const short = visitShort(v);
      return (
        <span className="tnum block">
          <span className="block">{fmtShort(v.date)}{stale}</span>
          {short === full ? (
            <span className="block text-[12px] leading-snug">{full}</span>
          ) : (
            <span className="block text-[12px] leading-snug">
              <span aria-hidden="true" title={full}>{short}</span>
              <span className="sr-only">{full}</span>
            </span>
          )}
        </span>
      );
    },
  },
  {
    id: "flags",
    header: inline ? "Facts, 12 months before the list date (our reading)" : "12 months before the list date (our reading)",
    accessorFn: (f) => (f.properties.flags ?? []).length,
    enableSorting: false,
    meta: {
      thWrap: inline,
      th: inline ? (beside ? "hidden" : "hidden xl:table-cell") : "",
      td: inline ? (beside ? "hidden" : "hidden min-w-[14rem] xl:table-cell") : "min-w-[10rem] max-w-[20rem]",
    },
    cell: ({ row }) => (inline
      ? <FactTags flags={row.original.properties.flags} />
      : <span className="text-[12px] leading-snug text-ink-2">{factsText(row.original.properties)}</span>),
  },
];

/**
 * The list of the places the filters leave, with a filter by name or street, sorting by any column,
 * pages of 50, a printout of every row and a CSV of every row. Two layouts: a drawer over the foot of
 * its positioned container, the map's row, with its own toggle (the public site), so a line in flow
 * under that row never covers it; or `inline`, the whole of its container (the staff site's List
 * view), where selecting anywhere on a row opens the place and the open place's row is marked. Inline:
 *  - `active`: false while another view shows; the list then counts as closed (a print is not its
 *    printout, and the print log is not told it is);
 *  - `beside`: a place's panel stands beside the list, which folds its last visit and its facts under
 *    each place's name at every width;
 *  - `onShowSummary`: in `bands` mode, the line on band 1's rate, above the rows and scrolling with
 *    them, links to the view with every band's;
 *  - `selectedId`: the open place, whose row and name are marked.
 */
export default function PlaceTable({
  facilities,
  filters,
  onSelect,
  openKey = null,
  openWhen = false,
  inline = false,
  active = true,
  beside = false,
  selectedId = null,
  onShowSummary = null,
}) {
  const { advanced } = useAdvanced();
  const meta = useMeta();
  const mode = useMode();
  const [drawerOpen, setOpen] = useState(Boolean(openKey));
  const open = inline ? active : drawerOpen;
  // Each time the address asks for the list (?list, a new key each time), it opens.
  useEffect(() => { if (openKey) setOpen(true); }, [openKey]);
  // When the map cannot load, the list opens in its place.
  useEffect(() => { if (openWhen) setOpen(true); }, [openWhen]);
  const [pageIndex, setPageIndex] = useState(0);
  const [sorting, setSorting] = useState([]);
  const [globalFilter, setGlobalFilter] = useState("");
  const select = (f) => { onSelect(f); if (!inline) setOpen(false); };
  const columns = useMemo(() => makeColumns({ mode, meta, onSelect: select, inline, beside }), [mode, meta, onSelect, inline, beside]);

  // The site's order (band, then points, then name; or name) until a header is chosen.
  const rowsIn = useMemo(() => {
    if (!facilities) return [];
    const feats = sortPlaces(facilities.features.filter((f) => passesFilters(f.properties, filters, { mode })), { mode });
    if (!globalFilter.trim()) return feats;
    return searchPlaces(feats, globalFilter, feats.length);
  }, [facilities, filters, globalFilter, mode]);
  // Every fact any listed place carries, for the closing note.
  const listFlags = useMemo(() => [...new Set(rowsIn.flatMap((f) => f.properties.flags ?? []))], [rowsIn]);

  const table = useReactTable({
    data: rowsIn,
    columns,
    // A row is its place, not its position: a search or a filter that hides a place removes its row.
    getRowId: (f) => String(f.properties.facility_id),
    meta: { selectedId },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    state: { pagination: { pageIndex, pageSize: PAGE_SIZE }, sorting },
    onSortingChange: (u) => { setSorting(u); setPageIndex(0); },
    onPaginationChange: (updater) => {
      const next = typeof updater === "function" ? updater({ pageIndex, pageSize: PAGE_SIZE }) : updater;
      setPageIndex(next.pageIndex);
    },
  });

  // Exactly what the list shows: its filters, its search and its order, every page. Logged on the staff site.
  function downloadCsv() {
    if (!facilities) return;
    saveCsv(table.getSortedRowModel().rows.map((r) => r.original), { meta, mode, filters });
  }

  const rows = table.getRowModel().rows;
  const total = rowsIn.length;
  const start = pageIndex * PAGE_SIZE + 1;
  const end = Math.min(start + PAGE_SIZE - 1, total);
  const pageCount = Math.ceil(total / PAGE_SIZE);

  // The printout: every row the list holds, in its order, rendered only while printing. "Print this
  // list" prints it alone (a place's panel is hidden for it); a print from the browser while the list
  // is open prints it too, unless a place's panel is open, which then prints instead.
  const [printing, setPrinting] = useState(false);
  const fromButton = useRef(false);
  const now = useRef({});
  now.current = { open, meta, filters, globalFilter, total };
  const listPrints = () => fromButton.current || (now.current.open && !document.querySelector(".print-sheet"));
  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const before = () => { if (!fromButton.current && listPrints()) flushSync(() => setPrinting(true)); };
    const after = () => {
      fromButton.current = false;
      document.body.classList.remove("printing-list");
      setPrinting(false);
    };
    window.addEventListener("beforeprint", before);
    window.addEventListener("afterprint", after);
    // What the staff site's print log records for it: the list's scope and date, and its row count.
    const stop = describePrints(() => {
      const s = now.current;
      return listPrints() ? { name: listPrintName(s.meta, s.filters, { search: s.globalFilter }), rows: s.total } : null;
    });
    return () => {
      window.removeEventListener("beforeprint", before);
      window.removeEventListener("afterprint", after);
      document.body.classList.remove("printing-list");
      stop();
    };
  }, []);
  function printList() {
    fromButton.current = true;
    document.body.classList.add("printing-list");
    flushSync(() => setPrinting(true));
    window.print();
  }

  // One phrase for the list's order, on screen (the caption) and on paper.
  const order = orderPhrase({ sorting, search: globalFilter, mode });
  const bandLine = inline && mode === "bands" && bandDefs(meta).length > 0;

  return (
    <>
      {printing && (
        <ListPrintout
          features={table.getSortedRowModel().rows.map((r) => r.original)}
          meta={meta}
          mode={mode}
          filters={filters}
          search={globalFilter}
          order={order}
        />
      )}

      {!inline && (
        <button
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-controls="place-table"
          className="print-hide absolute bottom-0 left-1/2 z-30 flex -translate-x-1/2 items-center gap-2 border border-b-0 border-rule-strong bg-paper px-5 text-[13px] font-medium text-ink-2 shadow-paper hover:text-ink md:left-[calc(50%+10.25rem)]"
          style={{ height: TOGGLE_HEIGHT }}
        >
          <svg width="13" height="10" viewBox="0 0 13 10" fill="none" aria-hidden="true">
            <rect x="0" y="0" width="13" height="2" fill="currentColor" />
            <rect x="0" y="4" width="13" height="2" fill="currentColor" />
            <rect x="0" y="8" width="13" height="2" fill="currentColor" />
          </svg>
          {advanced ? "Table" : "Full list"}
          <span className="tnum bg-paper-edge px-1.5 py-0.5 text-[12px] text-ink-2">{total.toLocaleString()}</span>
        </button>
      )}

      <div
        id="place-table"
        className={inline
          ? "print-hide flex h-full flex-col overflow-hidden bg-paper"
          : `print-hide absolute left-0 right-0 z-20 flex-col overflow-hidden border-t border-rule-strong bg-paper md:left-[20.5rem] ${open ? "flex" : "hidden"}`}
        style={inline ? undefined : { bottom: TOGGLE_HEIGHT, height: DRAWER_HEIGHT }}
      >
        <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b border-rule px-5 py-2.5">
          {/* Inline, narrow enough that the toolbar keeps one line beside an open place (the list is 576px or more then). */}
          <div className={`relative flex-1 ${inline ? "min-w-[13rem] max-w-md" : "max-w-xs"}`}>
            <input
              type="text"
              placeholder="Filter this list by name or street"
              value={globalFilter}
              onChange={(e) => { setGlobalFilter(e.target.value); setPageIndex(0); }}
              aria-label="Filter this list by name or street"
              className="w-full border border-rule-strong bg-paper-sunk px-3 py-1.5 text-[14px] text-ink placeholder-ink-3 focus:border-ink focus:bg-paper focus:outline-none"
            />
          </div>
          <span className="tnum ml-auto text-[13px] text-ink-2" role="status">{total.toLocaleString()} {total === 1 ? "place" : "places"}</span>
          <button onClick={printList} disabled={total === 0} className="border border-ink px-3 py-1.5 text-[13px] font-semibold text-ink hover:bg-paper-edge disabled:cursor-not-allowed disabled:opacity-40">
            Print this list
          </button>
          <button onClick={downloadCsv} className="border border-ink bg-ink px-3 py-1.5 text-[13px] font-semibold text-paper hover:border-ink-2 hover:bg-ink-2">
            {inline ? "Download CSV" : <>Download {total === 1 ? "this place" : `these ${total.toLocaleString()} places`} (CSV)</>}
          </button>
        </div>

        <div className="flex-1 overflow-auto scroll-pt-[4.5rem]">
          {/* What a band is, as a group rate, where the list opens (every band's rate is on the Summary view).
              It scrolls with the rows, so on a short screen, or beside an open place, it gives them its room. */}
          {bandLine && (
            <p className="border-b border-rule px-5 py-2 text-[12.5px] leading-[1.45] text-ink-2">
              {bandSummary(meta, "1")}
              {onShowSummary && (
                <>
                  {" "}
                  <button type="button" onClick={onShowSummary} className="whitespace-nowrap border-b border-ink/25 text-ink-2 hover:border-ink hover:text-ink">
                    Every band&rsquo;s rate: Summary
                  </button>
                </>
              )}
            </p>
          )}
          <table className="w-full text-sm">
            <caption className="sr-only">Listed places, {order}. Select a place&rsquo;s name to open it.</caption>
            <thead className="sticky top-0 border-b border-rule-strong bg-paper">
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id}>
                  {hg.headers.map((header) => {
                    const canSort = header.column.getCanSort();
                    const dir = header.column.getIsSorted();
                    const label = flexRender(header.column.columnDef.header, header.getContext());
                    const colMeta = header.column.columnDef.meta;
                    return (
                      <th key={header.id} scope="col" aria-sort={dir === "asc" ? "ascending" : dir === "desc" ? "descending" : canSort ? "none" : undefined} className={`label px-4 py-2.5 text-left align-bottom first:pl-5 ${colMeta?.thWrap ? "" : "whitespace-nowrap"} ${colMeta?.th ?? ""}`}>
                        {canSort ? (
                          <button onClick={header.column.getToggleSortingHandler()} className="label inline-flex items-center gap-1 hover:text-ink">
                            {label}
                            <span aria-hidden="true">{dir === "asc" ? "↑" : dir === "desc" ? "↓" : ""}</span>
                          </button>
                        ) : label}
                      </th>
                    );
                  })}
                </tr>
              ))}
            </thead>
            <tbody>
              {rows.map((row) => {
                // The open place's row: its background and, since that is faint on paper, an ink bar at its left edge.
                const on = selectedId != null && row.original.properties.facility_id === selectedId;
                return (
                  <tr
                    key={row.id}
                    onClick={inline ? () => select(row.original) : undefined}
                    className={`border-b border-rule align-top ${inline ? "cursor-pointer" : ""} ${on ? "bg-paper-edge" : "hover:bg-paper-sunk"}`}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className={`px-4 py-2 text-[13px] text-ink-2 first:pl-5 ${on ? "first:shadow-[inset_3px_0_0_#17150F]" : ""} ${cell.column.columnDef.meta?.td ?? "whitespace-nowrap"}`}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
          {total === 0 && (
            <p className="px-5 py-6 text-[14px] text-ink-2" role="status">
              No listed place matches these filters. {mode === "bands" ? "Include more bands, or " : ""}Pick a different kind of place or finding.
            </p>
          )}
          {total > 0 && (
            <p className="px-5 py-3 text-[13px] leading-[1.5] text-ink-2">
              Grades are the County&rsquo;s latest on record for each place. {gradeContextSentence(meta)}{" "}
              {factsNote(!inline ? FACTS_IN_LAST_COLUMN : beside ? FACTS_UNDER_NAME : FACTS_EITHER_PLACE, listFlags)}
            </p>
          )}
        </div>

        <div className="flex shrink-0 flex-wrap items-center justify-between gap-x-3 gap-y-1 border-t border-rule px-5 py-2 text-[13px] text-ink-2">
          <span>{total === 0 ? "No results" : `${start} to ${end} of ${total.toLocaleString()}`}</span>
          <div className="flex items-center gap-2">
            <span>Page {pageCount === 0 ? "0" : pageIndex + 1} of {pageCount}</span>
            <button onClick={() => setPageIndex((p) => Math.max(0, p - 1))} disabled={pageIndex === 0} className="border border-rule-strong px-2.5 py-1 hover:bg-paper-edge hover:text-ink disabled:cursor-not-allowed disabled:opacity-40">
              Previous
            </button>
            <button onClick={() => setPageIndex((p) => Math.min(pageCount - 1, p + 1))} disabled={pageIndex >= pageCount - 1} className="border border-rule-strong px-2.5 py-1 hover:bg-paper-edge hover:text-ink disabled:cursor-not-allowed disabled:opacity-40">
              Next
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

/**
 * The list on paper (print only): what it holds, in which order (`order`, the caption's phrase) and
 * when it was drawn up, the use rule on the staff site (the invented-sample and student notes
 * elsewhere), in `bands` mode each printed band's rate as a group, then every row, in the list's order,
 * and what the grades and the facts are.
 */
export function ListPrintout({ features, meta, mode, filters, search = "", order }) {
  const n = features.length;
  const cols = listPrintColumns({ mode });
  const rows = listPrintRows(features, { meta, mode });
  const dates = [
    meta?.generated && `Drawn up ${fmtDate(meta.generated)}`,
    meta?.inspections_through && `inspections through ${fmtDate(meta.inspections_through)}`,
    meta?.expires && `do not use after ${fmtDate(meta.expires)}`,
  ].filter(Boolean).join("; ");
  const bands = mode === "bands"
    ? [...new Set(features.map((f) => shownBand(f.properties, { mode })).filter(Boolean))].sort((a, b) => Number(a) - Number(b))
    : [];
  const flags = [...new Set(features.flatMap((f) => f.properties.flags ?? []))];
  return (
    <section className="print-only print-list w-full px-1 py-2 text-[10.5px] leading-[1.35] text-ink">
      <h2 className="font-serif text-[17px] font-medium">{SITE.siteTitle}: the listed places</h2>
      <p className="mt-1">{listScope(filters, { mode, search })} {n.toLocaleString()} {n === 1 ? "place" : "places"}, {order ?? orderPhrase({ search, mode })}.</p>
      {dates && <p className="mt-0.5">{dates}.</p>}
      <p className="mt-0.5">
        {isStaff(meta) ? `${USE_NOTE} ${PUBLIC_RECORD_NOTE}` : `${meta?.sample ? "Every place, address and figure in it is invented. " : ""}${STUDENT_NOTE}`}
      </p>
      {bands.length > 0 && <p className="mt-0.5">{bands.map((b) => bandSummary(meta, b)).join(" ")}</p>}
      <table className="mt-2 w-full border-collapse text-left">
        <thead>
          <tr className="border-b border-ink">
            {cols.map((c) => <th key={c} scope="col" className="py-1 pr-2 align-bottom font-semibold">{c}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={features[i]?.properties?.facility_id ?? i} className="border-b border-rule align-top">
              {r.map((c, j) => <td key={j} className="whitespace-pre-line py-0.5 pr-2">{c}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      {n > 0 && (
        <p className="mt-2">
          Grades are the County&rsquo;s latest on record for each place. {gradeContextSentence(meta)} {factsNote(FACTS_IN_LAST_COLUMN, flags)}
        </p>
      )}
    </section>
  );
}
