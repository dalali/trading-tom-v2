import React from "react";
import Modal from "./Modal";

/** Generic confirm dialog — docs/design.md Section 2.4 modal conventions.
 * `destructive` swaps the confirm button to the solid loss-600 style
 * (reserved for the confirm dialog's final button per Section 2.4). */
export default function ConfirmDialog({ title, children, confirmLabel, destructive, busy, onConfirm, onClose }) {
  return (
    <Modal
      title={title}
      onClose={onClose}
      busy={busy}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            type="button"
            className={destructive ? "btn btn-destructive-solid" : "btn btn-primary"}
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? "Working…" : confirmLabel}
          </button>
        </>
      }
    >
      {children}
    </Modal>
  );
}
