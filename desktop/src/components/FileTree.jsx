import React, { useMemo } from "react";
import { Tree } from "react-arborist";
import { ChevronDown, ChevronRight, File, Folder } from "lucide-react";

function buildTree(files) {
  const root = { id: "__root__", name: "全部文件", kind: "folder", children: [] };
  const folders = new Map([["", root]]);
  for (const file of files) {
    const parts = file[4].split("/");
    let parent = root;
    let path = "";
    parts.forEach((part, index) => {
      path = path ? `${path}/${part}` : part;
      const isFile = index === parts.length - 1;
      if (isFile) {
        parent.children.push({ id: file[4], name: part, kind: "file", file });
      } else {
        if (!folders.has(path)) {
          const folder = { id: path, name: part, kind: "folder", children: [] };
          folders.set(path, folder);
          parent.children.push(folder);
        }
        parent = folders.get(path);
      }
    });
  }
  const sort = (nodes) => nodes.sort((a, b) => (a.kind !== b.kind ? (a.kind === "folder" ? -1 : 1) : a.name.localeCompare(b.name, "zh-CN")));
  const visit = (node) => { sort(node.children); node.children.filter((child) => child.kind === "folder").forEach(visit); };
  visit(root);
  return root;
}

export default function FileTree({ files, selected, onSelect }) {
  const tree = useMemo(() => buildTree(files), [files]);
  return <div className="managed-file-tree">
    <Tree data={[tree]} width="100%" height={420} rowHeight={34} indent={18} openByDefault>
      {({ node, style }) => <button type="button" className={`managed-tree-row ${selected === node.id ? "selected" : ""}`} style={style} onClick={() => {
        if (node.data.kind === "file") onSelect(node.data.file[4]);
        else node.toggle();
      }}>
        {node.data.kind === "folder" ? (node.isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />) : <span className="tree-spacer" />}
        {node.data.kind === "folder" ? <Folder size={15} /> : <File size={15} />}
        <span>{node.data.name}</span>
      </button>}
    </Tree>
  </div>;
}
