import { useEffect, useState } from "react";
import { api } from "../api";
import type { SupplierInfo } from "../types";

function Stars({ value, onChange }: { value: number | null; onChange: (v: number | null) => void }) {
  return (
    <span className="inline-flex">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          className={`px-0.5 text-base leading-none ${value !== null && n <= value ? "text-amber-500" : "text-slate-300 dark:text-slate-600"}`}
          title={`${n} of 5`}
          onClick={() => onChange(value === n ? null : n)}
        >
          ★
        </button>
      ))}
    </span>
  );
}

export default function SupplierRatings({ refreshKey }: { refreshKey: number }) {
  const [suppliers, setSuppliers] = useState<SupplierInfo[]>([]);
  const [newName, setNewName] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.suppliers().then(setSuppliers).catch((e: Error) => setError(e.message));
  }, [refreshKey]);

  async function save(s: SupplierInfo, change: Partial<SupplierInfo>) {
    const next = { ...s, ...change };
    setSuppliers((list) => list.map((x) => (x.name === s.name ? next : x)));
    try {
      await api.rateSupplier(s.name, {
        quality: next.quality,
        delivery: next.delivery,
        preferred: next.preferred,
        notes: next.notes,
      });
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function add() {
    const name = newName.trim();
    if (!name) return;
    await save({ name, quality: null, delivery: null, preferred: false, notes: null, price_list_items: 0 }, {});
    setNewName("");
    setSuppliers(await api.suppliers());
  }

  return (
    <section className="card overflow-x-auto">
      <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 p-3 dark:border-slate-800">
        <div>
          <h2 className="font-semibold">Supplier ratings</h2>
          <p className="text-xs text-slate-500">
            Your experience with each supplier counts in the sourcing score (15% by default). Preferred suppliers win
            ties.
          </p>
        </div>
        <div className="ml-auto flex gap-2">
          <input
            className="input w-48"
            placeholder="Add a supplier…"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && add()}
          />
          <button className="btn-secondary" disabled={!newName.trim()} onClick={add}>
            Add
          </button>
        </div>
      </div>
      {error && <p className="px-3 py-2 text-sm text-red-600">{error}</p>}
      {suppliers.length === 0 ? (
        <p className="p-3 text-sm text-slate-500">Import a price list or add a supplier to rate it.</p>
      ) : (
        <table className="w-full">
          <thead>
            <tr>
              <th className="th">Supplier</th>
              <th className="th">Items in your list</th>
              <th className="th">Quality</th>
              <th className="th">Delivery reliability</th>
              <th className="th">Preferred</th>
              <th className="th">Notes</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {suppliers.map((s) => (
              <tr key={s.name}>
                <td className="td font-medium">{s.name}</td>
                <td className="td">{s.price_list_items || "—"}</td>
                <td className="td">
                  <Stars value={s.quality} onChange={(v) => save(s, { quality: v })} />
                </td>
                <td className="td">
                  <Stars value={s.delivery} onChange={(v) => save(s, { delivery: v })} />
                </td>
                <td className="td">
                  <input type="checkbox" checked={s.preferred} onChange={(e) => save(s, { preferred: e.target.checked })} />
                </td>
                <td className="td">
                  <input
                    className="w-full rounded border border-transparent bg-transparent px-1 py-0.5 text-sm hover:border-slate-300 focus:border-amber-500 focus:outline-none dark:hover:border-slate-700"
                    defaultValue={s.notes ?? ""}
                    placeholder="—"
                    onBlur={(e) => e.target.value !== (s.notes ?? "") && save(s, { notes: e.target.value || null })}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
