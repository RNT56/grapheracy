export interface GraphRendererAdapter {
  mount(container: HTMLElement): void;
  unmount(): void;
  setData(data: unknown): void;
  focusNode(nodeId: string): void;
}
