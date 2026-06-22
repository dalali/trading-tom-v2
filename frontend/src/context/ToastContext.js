import React, { createContext, useCallback, useContext, useRef, useState } from "react";

// Toast conventions — docs/design.md Section 2.4 / 5.4.
// success/info auto-dismiss after 5s; error persists until dismissed.
const ToastContext = createContext(null);
let idCounter = 0;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const timers = useRef({});

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    if (timers.current[id]) {
      clearTimeout(timers.current[id]);
      delete timers.current[id];
    }
  }, []);

  const showToast = useCallback(
    (message, variant = "info") => {
      const id = ++idCounter;
      setToasts((prev) => {
        const next = [...prev, { id, message, variant }];
        // max 3 stacked (Section 2.4)
        return next.slice(-3);
      });
      if (variant !== "error") {
        timers.current[id] = setTimeout(() => dismiss(id), 5000);
      }
      return id;
    },
    [dismiss]
  );

  return (
    <ToastContext.Provider value={{ showToast, dismiss }}>
      {children}
      <div className="toast-stack" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.variant}`} role="status">
            <span>{t.message}</span>
            <button
              type="button"
              className="toast-close"
              aria-label="Dismiss notification"
              onClick={() => dismiss(t.id)}
            >
              &times;
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return ctx;
}
