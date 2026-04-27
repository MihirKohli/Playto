import Badge from "./Badge";
import { toRupees, fmtDate } from "../utils";

export default function LedgerTable({ entries }) {
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Type</th><th>Amount</th><th>Status</th><th>Description</th><th>Date</th>
        </tr>
      </thead>
      <tbody>
        {entries.length === 0 ? (
          <tr className="no-rows"><td colSpan={5}>no ledger entries</td></tr>
        ) : entries.map((e) => (
          <tr key={e.id}>
            <td><Badge label={e.entry_type} filled={e.entry_type === "CREDIT"} /></td>
            <td>{toRupees(e.amount_paise)}</td>
            <td><Badge label={e.status} filled={e.status === "SETTLED"} /></td>
            <td>{e.description}</td>
            <td>{fmtDate(e.created_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
