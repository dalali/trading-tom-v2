import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchUsers, deactivateUser } from "../../api/endpoints";
import { useFetch } from "../../utils/useFetch";
import LoadingSkeleton from "../../components/LoadingSkeleton";
import ErrorState from "../../components/ErrorState";
import EmptyState from "../../components/EmptyState";
import Badge from "../../components/Badge";
import Money from "../../components/Money";
import CreateUserModal from "../../components/CreateUserModal";
import FundAccountModal from "../../components/FundAccountModal";
import ConfirmDialog from "../../components/ConfirmDialog";
import { useToast } from "../../context/ToastContext";
import { adminUserDetailPath } from "../../routes/paths";

/** Admin user management list — docs/design.md Section 4.5. */
export default function UserList() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [tab, setTab] = useState("active");
  const [search, setSearch] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [fundTarget, setFundTarget] = useState(null);
  const [deactivateTarget, setDeactivateTarget] = useState(null);
  const [deactivating, setDeactivating] = useState(false);
  const [openMenuId, setOpenMenuId] = useState(null);

  const { data, loading, error, refetch } = useFetch(
    () => fetchUsers({ status: tab, q: search || undefined, page: 1, page_size: 100 }),
    [tab, search]
  );

  async function handleDeactivate() {
    setDeactivating(true);
    try {
      await deactivateUser(deactivateTarget.id);
      showToast(`${deactivateTarget.display_name} deactivated.`, "success");
      setDeactivateTarget(null);
      refetch();
    } catch (err) {
      showToast(err.message || "Couldn't deactivate this user.", "error");
    } finally {
      setDeactivating(false);
    }
  }

  return (
    <div>
      <div className="card-header" style={{ marginBottom: "var(--space-4)" }}>
        <h1 className="text-h1" style={{ margin: 0 }}>
          Users
        </h1>
        <button type="button" className="btn btn-primary" onClick={() => setCreateOpen(true)}>
          + Create User
        </button>
      </div>

      <div style={{ display: "flex", gap: "var(--space-2)", marginBottom: "var(--space-4)" }}>
        <button
          type="button"
          className={tab === "active" ? "btn btn-primary" : "btn btn-secondary"}
          onClick={() => setTab("active")}
        >
          Active
        </button>
        <button
          type="button"
          className={tab === "deactivated" ? "btn btn-primary" : "btn btn-secondary"}
          onClick={() => setTab("deactivated")}
        >
          Deactivated
        </button>
      </div>

      <div className="form-field" style={{ maxWidth: 320 }}>
        <input
          className="form-input"
          placeholder="Search by name or email…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Search users"
        />
      </div>

      {loading && <LoadingSkeleton rows={6} />}
      {!loading && error && <ErrorState message={error} onRetry={refetch} />}

      {!loading && !error && data && data.items.length === 0 && (
        <EmptyState
          title={tab === "active" ? "Only your admin account exists so far." : "No deactivated users."}
          description={tab === "active" ? "Create a user to get started." : undefined}
          action={
            tab === "active" && (
              <button type="button" className="btn btn-primary" onClick={() => setCreateOpen(true)}>
                + Create User
              </button>
            )
          }
        />
      )}

      {!loading && !error && data && data.items.length > 0 && (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Role</th>
                <th className="col-num">Total Value</th>
                <th className="col-center">Status</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {data.items.map((u) => {
                const isUnfunded = Number(u.total_value) === 0 && u.is_active;
                return (
                  <tr key={u.id} className="clickable" onClick={() => navigate(adminUserDetailPath(u.id))}>
                    <td className="text-strong">{u.display_name}</td>
                    <td>{u.email}</td>
                    <td>{u.role === "admin" ? "Admin" : "User"}</td>
                    <td className="col-num">
                      <Money value={u.total_value} />
                    </td>
                    <td className="col-center">
                      {u.is_active ? (
                        <Badge variant="success">{isUnfunded ? "Active - Unfunded" : "Active"}</Badge>
                      ) : (
                        <Badge variant="muted">Deactivated</Badge>
                      )}
                    </td>
                    <td onClick={(e) => e.stopPropagation()} style={{ position: "relative" }}>
                      <button
                        type="button"
                        className="btn btn-ghost"
                        aria-haspopup="menu"
                        aria-expanded={openMenuId === u.id}
                        onClick={() => setOpenMenuId(openMenuId === u.id ? null : u.id)}
                      >
                        ⋯
                      </button>
                      {openMenuId === u.id && (
                        <div
                          role="menu"
                          className="card"
                          style={{
                            position: "absolute",
                            right: 0,
                            top: "100%",
                            zIndex: 10,
                            padding: "var(--space-2)",
                            minWidth: 160,
                          }}
                        >
                          <button
                            type="button"
                            role="menuitem"
                            className="btn btn-ghost"
                            style={{ display: "block", width: "100%", textAlign: "left", padding: "var(--space-2)" }}
                            onClick={() => {
                              setOpenMenuId(null);
                              navigate(adminUserDetailPath(u.id));
                            }}
                          >
                            View
                          </button>
                          {u.is_active && (
                            <>
                              <button
                                type="button"
                                role="menuitem"
                                className="btn btn-ghost"
                                style={{ display: "block", width: "100%", textAlign: "left", padding: "var(--space-2)" }}
                                onClick={() => {
                                  setOpenMenuId(null);
                                  setFundTarget(u);
                                }}
                              >
                                Fund Account
                              </button>
                              <button
                                type="button"
                                role="menuitem"
                                className="btn btn-ghost"
                                style={{
                                  display: "block",
                                  width: "100%",
                                  textAlign: "left",
                                  padding: "var(--space-2)",
                                  color: "var(--loss-600)",
                                }}
                                onClick={() => {
                                  setOpenMenuId(null);
                                  setDeactivateTarget(u);
                                }}
                              >
                                Deactivate
                              </button>
                            </>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {createOpen && (
        <CreateUserModal
          onClose={() => setCreateOpen(false)}
          onCreated={() => {
            setCreateOpen(false);
            refetch();
          }}
        />
      )}

      {fundTarget && (
        <FundAccountModal
          user={fundTarget}
          currentBalance={fundTarget.total_value}
          onClose={() => setFundTarget(null)}
          onFunded={() => {
            setFundTarget(null);
            refetch();
          }}
        />
      )}

      {deactivateTarget && (
        <ConfirmDialog
          title={`Deactivate ${deactivateTarget.display_name}?`}
          confirmLabel="Deactivate"
          destructive
          busy={deactivating}
          onConfirm={handleDeactivate}
          onClose={() => setDeactivateTarget(null)}
        >
          <p>
            {deactivateTarget.display_name} will no longer be able to log in. Their trade history remains visible
            to admins, and any open positions will stop updating but will not be sold.
          </p>
        </ConfirmDialog>
      )}
    </div>
  );
}
