import { Component, type ReactNode } from "react";
export class TerminalBoundary extends Component<
  { children: ReactNode },
  { error: boolean }
> {
  state = { error: false };
  static getDerivedStateFromError() {
    return { error: true };
  }
  render() {
    return this.state.error ? (
      <section className="panel loading" role="alert">
        <h2>Terminal payload could not be rendered</h2>
        <p>
          PAYLOAD ERROR · Refresh to reconnect and request a current snapshot.
        </p>
      </section>
    ) : (
      this.props.children
    );
  }
}
