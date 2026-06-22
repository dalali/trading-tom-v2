import React from "react";

/** Shared pagination convention — docs/design.md Section 5.2. */
export default function Pagination({ page, pageSize, total, onPageChange, onPageSizeChange }) {
  const totalPages = Math.max(Math.ceil(total / pageSize), 1);
  return (
    <div className="pagination">
      <button
        type="button"
        className="btn btn-secondary"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
      >
        ◂ Prev
      </button>
      <span>
        Page {page} of {totalPages}
      </span>
      <button
        type="button"
        className="btn btn-secondary"
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
      >
        Next ▸
      </button>
      {onPageSizeChange && (
        <select
          aria-label="Rows per page"
          value={pageSize}
          onChange={(e) => onPageSizeChange(Number(e.target.value))}
        >
          {[25, 50, 100].map((size) => (
            <option key={size} value={size}>
              {size} /pg
            </option>
          ))}
        </select>
      )}
    </div>
  );
}
