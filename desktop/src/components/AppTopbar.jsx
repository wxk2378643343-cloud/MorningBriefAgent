import React from "react";

export default function AppTopbar({ eyebrow, title, serviceState, serviceLabel }) {
  return (
    <header className="topbar">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
      </div>
      <div className={`connection connection-${serviceState}`}>
        <span className="pulse" />
        {serviceLabel}
      </div>
    </header>
  );
}
