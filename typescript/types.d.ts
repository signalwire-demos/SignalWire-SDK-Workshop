// types.d.ts
// Minimal shim for the SignalWire SDK TypeScript surface.
//
// @signalwire/agents does not exist on npm (the SDK is Python-only as of
// workshop build time). This shim documents what the conceptual TS equivalents
// look like and lets tsc --noEmit pass on the reference-only step files.
//
// Workshop runtime is Python. These files exist so attendees can read the
// same agent expressed in TypeScript and understand the conceptual mapping.

declare module "@signalwire/agents" {
  export interface LanguageOptions {
    name: string;
    code: string;
    voice: string;
    speechFillers?: string[];
    functionFillers?: string[] | Record<string, string[]>;
  }

  export interface PromptSection {
    body?: string;
    bullets?: string[];
  }

  export interface ToolDefinition {
    name: string;
    description: string;
    parameters: object;
    handler: (args: Record<string, unknown>, rawData: unknown) => FunctionResult | Promise<FunctionResult>;
    fillers?: Record<string, string[]>;
  }

  export class FunctionResult {
    constructor(text: string);
  }

  export { FunctionResult as SwaigFunctionResult };

  export class DataMap {
    constructor(name: string);
    description(desc: string): this;
    parameter(
      name: string,
      type: string,
      desc: string,
      opts?: { required?: boolean }
    ): this;
    webhook(method: string, url: string): this;
    output(result: FunctionResult): this;
    fallbackOutput(result: FunctionResult): this;
    toSwaigFunction(): unknown;
  }

  export class AgentBase {
    constructor(opts: { name: string; route?: string });
    addLanguage(opts: LanguageOptions): void;
    addHints(hints: string[]): void;
    setParams(params: Record<string, unknown>): void;
    promptAddSection(title: string, body: string | PromptSection): void;
    defineTool(opts: ToolDefinition): void;
    registerSwaigFunction(fn: unknown): void;
    addSkill(name: string, config?: Record<string, unknown>): void;
    setPostPrompt(prompt: string): void;
    onSummary?(summary: unknown, rawData: unknown): void;
  }
}

// @signalwire/realtime-api is published on npm with partial type declarations.
// This shim covers the Relay WebSocket client pattern used in
// step13_relay_demo.ts. The published package uses a different factory-function
// style; this shim mirrors the Python relay.Client class style for teaching
// story consistency.
declare module "@signalwire/relay" {
  export interface CallHandle {
    id: string;
    state: string;
    fromNumber: string;
    toNumber: string;
    answer(): Promise<void>;
    on(event: string, handler: (...args: unknown[]) => void): void;
  }

  export interface CallingNamespace {
    on(event: "call.received", handler: (call: CallHandle) => Promise<void>): void;
    dial(opts: { from_: string; to: string }): Promise<CallHandle>;
  }

  export class Client {
    constructor(opts: { project: string; token: string });
    calling: CallingNamespace;
    connect(): Promise<void>;
    run(): Promise<void>;
  }
}
