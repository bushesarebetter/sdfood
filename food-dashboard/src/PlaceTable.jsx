import { useState, useMemo, useEffect } from "react";
import { useReactTable, getCoreRowModel, getSortedRowModel, getPaginationRowModel, flexRender } from "@tanstack/react-table";
import { facilitiesToCsv } from "./lib/format";
import { useAdvanced } from "./useAdvanced";
import { useMeta, useMode } from "./useMeta";
import { passesFilters, sortPlaces, shownPoints } from "./lib/filters";
import { FLAG_LABELS, typeLabel, visitLabel } from "./lib/inspections";
import { gradeView } from "./lib/grades";
import { markFor, shownBand } from "./lib/marks";
import { searchPlaces } from "./lib/search";
import { fmtShort } from "./lib/dates";
import { gradeContextSentence } from "./lib/framing";

const PAGE_SIZE = 50;
const DRAWER_HEIGHT = "44vh";
const TOGGLE_HEIGHT = 40;

/**
 * The columns, all from the index. `bands` mode leads with the band and the
 * points (where the export gives them); `record` mode has neither. There is
 * no position column in any mode. The grade is gradeView's, as everywhere.
 */
const makeColumns = ({ mode, onSelect }) => [
  ...(mode === "bands"
    ? [
        {
          id: "band",
          header: "Band",
          accessorFn: (f) => Number(shownBand(f.properties, { mode })) || 99,
          cell: ({ row }) => {
            const m = markFor(row.original.properties, { mode });
            return <span className="tnum font-semibold" style={{ color: m.text ?? undefined }}>{m.label ?? ""}</span>;
          },
        },
        {
          id: "points",
          header: "Points",
          accessorFn: (f) => shownPoints(f.properties, { mode }) ?? -1,
          cell: ({ row }) => <span className="tnum text-ink">{shownPoints(row.original.properties, { mode }) ?? ""}</span>,
        },
      ]
    : []),
  {
    id: "name",
    header: "Place",
    accessorFn: (f) => f.properties.name,
    cell: ({ row, getValue }) => (
      <button onClick={() => onSelect(row.original)} className="block text-left hover:underline focus:underline">
        <span className="block text-ink">{getValue()}</span>
        <span className="block text-[12px] text-ink-2">{row.original.properties.address}</span>
      </button>
    ),
  },
  { id: "type", header: "Kind", accessorFn: (f) => typeLabel(f.properties.facility_type) },
  {
    id: "district",
    header: "District",
    accessorFn: (f) => f.properties.council_district ?? 0,
    cell: ({ getValue }) => <span className="tnum">{getValue() ? `D${getValue()}` : ""}</span>,
  },
  {
    id: "grade",
    header: "Latest grade",
    accessorFn: (f) => f.properties.grade?.date ?? "",
    cell: ({ row }) => {
      const g = gradeView(row.original.properties.grade);
      return <span className="tnum font-semibold" style={g.textColor ? { color: g.textColor } : undefined}>{g.graded ? g.short : <span className="font-normal text-ink-2">{g.text.toLowerCase()}</span>}</span>;
    },
  },
  {
    id: "last",
    header: "Last visit",
    accessorFn: (f) => f.properties.last_visit?.date ?? "",
    cell: ({ row }) => {
      const v = row.original.properties.last_visit;
      return v ? <span className="tnum">{fmtShort(v.date)}, {visitLabel(v.type)}</span> : "";
    },
  },
  {
    id: "flags",
    header: "Last 12 months (our reading)",
    accessorFn: (f) => (f.properties.flags ?? []).length,
    enableSorting: false,
    cell: ({ row }) => <span className="text-[12px] text-ink-2">{(row.original.properties.flags ?? []).map((k) => FLAG_LABELS[k] ?? k).join("; ")}</span>,
  },
];

export default function PlaceTable({ facilities, filters, onSelect, initialOpen = false, openWhen = false }) {
  const { advanced } = useAdvanced();
  const meta = useMeta();
  const mode = useMode();
  const [open, setOpen] = useState(initialOpen);
  // When the map cannot load, the list opens in its place.
  useEffect(() => { if (openWhen) setOpen(true); }, [openWhen]);
  const [pageIndex, setPageIndex] = useState(0);
  const [sorting, setSorting] = useState([]);
  const [globalFilter, setGlobalFilter] = useState("");
  const select = (f) => { onSelect(f); setOpen(false); };
  const columns = useMemo(() => makeColumns({ mode, onSelect: select }), [mode, onSelect]);

  // The site's order (band, then points, then name; or name) until a header is chosen.
  const rowsIn = useMemo(() => {
    if (!facilities) return [];
    const feats = sortPlaces(facilities.features.filter((f) => passesFilters(f.properties, filters, { mode })), { mode });
    if (!globalFilter.trim()) return feats;
    return searchPlaces(feats, globalFilter, feats.length);
  }, [facilities, filters, globalFilter, mode]);

  const table = useReactTable({
    data: rowsIn,
    columns,
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

  function downloadCsv() {
    if (!facilities) return;
    const blob = new Blob([facilitiesToCsv(sortPlaces(facilities.features, { mode }), { meta, mode })], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `food-inspection-record-${meta?.generated ?? "export"}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const rows = table.getRowModel().rows;
  const total = rowsIn.length;
  const start = pageIndex * PAGE_SIZE + 1;
  const end = Math.min(start + PAGE_SIZE - 1, total);
  const pageCount = Math.ceil(total / PAGE_SIZE);

  return (
    <>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls="place-table"
        className="fixed bottom-0 left-1/2 z-30 flex -translate-x-1/2 items-center gap-2 border border-b-0 border-rule-strong bg-paper px-5 text-[13px] font-medium text-ink-2 shadow-paper hover:text-ink md:left-[calc(50%+10.25rem)]"
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

      <div
        id="place-table"
        className={`fixed left-0 right-0 z-20 flex-col overflow-hidden border-t border-rule-strong bg-paper md:left-[20.5rem] ${open ? "flex" : "hidden"}`}
        style={{ bottom: TOGGLE_HEIGHT, height: DRAWER_HEIGHT }}
      >
        <div className="flex shrink-0 items-center gap-3 border-b border-rule px-5 py-2.5">
          <div className="relative max-w-xs flex-1">
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
          <button onClick={downloadCsv} className="border border-ink bg-ink px-3 py-1.5 text-[13px] font-semibold text-paper hover:border-ink-2 hover:bg-ink-2">
            Download CSV
          </button>
        </div>

        <div className="flex-1 overflow-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Listed places{mode === "bands" ? ", by band, then points, then name" : ", by name"}. Select a place&rsquo;s name to open it.</caption>
            <thead className="sticky top-0 border-b border-rule-strong bg-paper">
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id}>
                  {hg.headers.map((header) => {
                    const canSort = header.column.getCanSort();
                    const dir = header.column.getIsSorted();
                    const label = flexRender(header.column.columnDef.header, header.getContext());
                    return (
                      <th key={header.id} scope="col" aria-sort={dir === "asc" ? "ascending" : dir === "desc" ? "descending" : canSort ? "none" : undefined} className="label whitespace-nowrap px-5 py-2.5 text-left">
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
              {rows.map((row) => (
                <tr key={row.id} className="border-b border-rule hover:bg-paper-sunk">
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="whitespace-nowrap px-5 py-2 text-[13px] text-ink-2">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {total === 0 && (
            <p className="px-5 py-6 text-[14px] text-ink-2" role="status">
              No listed place matches these filters. {mode === "bands" ? "Include more bands, or " : ""}Pick a different kind of place or finding.
            </p>
          )}
          {total > 0 && <p className="px-5 py-3 text-[13px] leading-[1.5] text-ink-2">Grades are the County&rsquo;s latest on record for each place. {gradeContextSentence(meta)}</p>}
        </div>

        <div className="flex shrink-0 items-center justify-between border-t border-rule px-5 py-2 text-[13px] text-ink-2">
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
