import React, { useEffect, useRef } from "react";

/** Modal — docs/design.md Section 2.4 / 8.3. Closes on scrim click, Esc,
 * or Cancel — never on accidental outside-click while `busy` (an async
 * submit is in flight). Traps focus and restores it to the trigger on
 * close. */
export default function Modal({ title, onClose, busy = false, wide = false, children, footer }) {
  const cardRef = useRef(null);
  // Captured once at mount — the element to restore focus to on close.
  const triggerElement = useRef(document.activeElement).current;

  useEffect(() => {
    const card = cardRef.current;
    const focusable = card?.querySelector(
      'input, button, select, textarea, [href], [tabindex]:not([tabindex="-1"])'
    );
    focusable?.focus();

    function handleKeyDown(e) {
      if (e.key === "Escape" && !busy) {
        onClose();
        return;
      }
      if (e.key === "Tab" && card) {
        const focusables = card.querySelectorAll(
          'input, button, select, textarea, [href], [tabindex]:not([tabindex="-1"])'
        );
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      if (triggerElement && triggerElement.focus) {
        triggerElement.focus();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busy]);

  function handleScrimClick(e) {
    if (e.target === e.currentTarget && !busy) {
      onClose();
    }
  }

  return (
    <div className="modal-scrim" onMouseDown={handleScrimClick}>
      <div
        className={`modal-card ${wide ? "modal-wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        ref={cardRef}
      >
        <div className="modal-header">
          <h2 className="text-h2" style={{ margin: 0 }}>
            {title}
          </h2>
          <button
            type="button"
            className="modal-close"
            aria-label="Close"
            onClick={onClose}
            disabled={busy}
          >
            &times;
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  );
}
