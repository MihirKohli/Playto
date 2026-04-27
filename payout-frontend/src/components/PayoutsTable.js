import Badge from "./Badge";
import { toRupees, fmtDate } from "../utils";

export default function PayoutsTable({ payouts }) {
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Amount</th><th>Status</th><th>Attempts</th><th>Failure Reason</th><th>Created</th>
        </tr>
      </thead>
      <tbody>
        {payouts.length === 0 ? (
          <tr className="no-rows"><td colSpan={5}>no payouts yet</td></tr>
        ) : payouts.map((p) => (
          <tr key={p.id}>
            <td>{toRupees(p.amount_paise)}</td>
            <td><Badge label={p.status} filled={p.status === "COMPLETED"} /></td>
            <td>{p.attempt_count}</td>
            <td>{p.failure_reason || "—"}</td>
            <td>{fmtDate(p.created_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
