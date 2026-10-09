# Rovema factory sheet setup

Source: two factory downtime sheets supplied by the user on 9 October 2026. Scope explicitly confirmed as Rovema only.

The preset creates missing catalogue records, reuses case-insensitive matching IDs, enables and selects every confirmed preset on first installation, and saves the existing LineTech configuration. All writes share one transaction and record the named Management actor. A repeated installation preserves saved deselections rather than resetting the factory every time. Existing runs and fault history are untouched. No schema migration is required.

Machine groups: SBS / Bagger (BV1, BV2, shared equipment), X-ray, Case Packer, Robot Palletiser. Existing repository-confirmed names are retained for consistent identities; spelling is normalised for display (for example Ribbon tension).

Planned: Film Change BV1/BV2, Label Change BV1/BV2, routine X-ray CCP Check, Break. Product, Format and Size changes use the existing Changeover workflow. A CCP stop never records a passed check. Failed CCP checks and the listed equipment faults are unplanned.

Management can deselect a reason via its category checkbox, hide a category/component, or deactivate a planned reason. Save configuration and refresh HMI to publish those choices. The setup screen also offers direct machine creation/movement and explicit Planned/Unplanned selection when adding a reason.

The installation endpoint requires the existing Management session and an idempotency key. It rejects other lines and conflicting planned/fault classifications, and rolls back on invalid references or audit failure. It does not fabricate product formats, pack weights, quality results or production standards.
