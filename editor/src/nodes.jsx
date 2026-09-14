import { Handle, Position } from "@xyflow/react";
import { nodeSummary } from "./graph.js";

function NodeCard({ kind, title, extra, children, selected }) {
  return (
    <article
      className={"rf-node" + (selected ? " selected" : "")}
      data-type={kind}
      data-loop={extra && extra.loopType}
      data-section={extra && extra.section}
      data-testid={"node-" + kind}
    >
      <header>{title}</header>
      <div className="body">{children}</div>
      <Handle type="target" position={Position.Left} className="handle in" isConnectable />
      <Handle type="source" position={Position.Right} className="handle out" isConnectable />
    </article>
  );
}

export function DataSourceNode({ data, selected }) {
  return (
    <NodeCard kind="dataSource" title={"📄 " + (data.label || data.id)} selected={selected}>
      {nodeSummary(data)}
    </NodeCard>
  );
}

export function LoopNode({ data, selected }) {
  return (
    <NodeCard kind="loop" title={"🔄 " + (data.label || data.id)} extra={{ loopType: data.loopType }} selected={selected}>
      {nodeSummary(data)}
    </NodeCard>
  );
}

export function FormulaNode({ data, selected }) {
  return (
    <NodeCard kind="formula" title={"📝 " + (data.label || data.id)} extra={{ section: data.section }} selected={selected}>
      {nodeSummary(data)}
    </NodeCard>
  );
}

export function AggregationNode({ data, selected }) {
  return (
    <NodeCard kind="aggregation" title={"📊 " + (data.label || data.id)} selected={selected}>
      {nodeSummary(data)}
    </NodeCard>
  );
}

export function ScopeNode({ data, selected }) {
  const collapsed = !!data.collapsed;
  const count = data.childCount || 0;
  return (
    <article
      className={"rf-node rf-scope" + (selected ? " selected" : "") + (collapsed ? " collapsed" : "")}
      data-type="scope"
      data-kind={data.scopeKind || "outer"}
      data-collapsed={collapsed ? "true" : "false"}
      data-testid="node-scope"
    >
      <header>
        <span>{"🪆 " + (data.label || data.id)}</span>
        <span className="scope-actions">
          <button
            type="button"
            data-testid="scope-toggle"
            onClick={(event) => {
              event.stopPropagation();
              if (data.onToggleScope) data.onToggleScope(data.id);
            }}
          >
            {collapsed ? "Expand" : "Collapse"}
          </button>
          <button
            type="button"
            data-testid="scope-drill"
            onClick={(event) => {
              event.stopPropagation();
              if (data.onDrillIn) data.onDrillIn(data.id);
            }}
          >
            Drill in
          </button>
        </span>
      </header>
      <div className="body">
        {nodeSummary(data)}
        {collapsed ? " · " + count + " nested" : ""}
      </div>
      <Handle type="target" position={Position.Left} className="handle in" isConnectable />
      <Handle type="source" position={Position.Right} className="handle out" isConnectable />
    </article>
  );
}

export const nodeTypes = {
  dataSource: DataSourceNode,
  loop: LoopNode,
  formula: FormulaNode,
  aggregation: AggregationNode,
  scope: ScopeNode,
};
