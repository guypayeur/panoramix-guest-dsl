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

export const nodeTypes = {
  dataSource: DataSourceNode,
  loop: LoopNode,
  formula: FormulaNode,
  aggregation: AggregationNode,
};
