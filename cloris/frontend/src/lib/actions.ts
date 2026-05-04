export function autoExpand(node: HTMLTextAreaElement) {
  function resize() {
    node.style.height = "auto";
    node.style.height = node.scrollHeight + "px";
  }

  node.addEventListener("input", resize);
  
  // Initial resize
  // Use setTimeout to ensure DOM is fully rendered
  setTimeout(resize, 0);

  return {
    destroy() {
      node.removeEventListener("input", resize);
    },
  };
}
