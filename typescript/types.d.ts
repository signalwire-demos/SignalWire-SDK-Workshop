// types.d.ts
// Minimal shim for the SignalWire SDK TypeScript surface.
//
// @signalwire/agents does not exist on npm (the SDK is Python-only as of
// workshop build time). @signalwire/node ships without a top-level types
// field and exposes a different API surface than the Python signalwire.rest
// module. This shim documents what conceptual TS equivalents would look like
// and lets tsc --noEmit pass on the reference-only step files.
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

// @signalwire/node is published on npm but ships without top-level TypeScript
// declarations in its package.json "types" field. This shim covers the
// four operations demonstrated in step12_rest_demo.ts.
declare module "@signalwire/node" {
  export interface PhoneNumber {
    sid: string;
    phoneNumber: string;
    friendlyName: string;
  }

  export interface Message {
    sid: string;
    status: string;
  }

  export interface Call {
    sid: string;
    from_: string;
    to: string;
    status: string;
    startTime: string;
  }

  export interface IncomingPhoneNumbersResource {
    list(opts?: { limit?: number; phoneNumber?: string }): Promise<PhoneNumber[]>;
    (sid: string): { update(opts: { voiceUrl: string }): Promise<unknown> };
  }

  export interface MessagesResource {
    create(opts: { from_: string; to: string; body: string }): Promise<Message>;
  }

  export interface CallsResource {
    list(opts?: { limit?: number }): Promise<Call[]>;
  }

  export class RestClient {
    constructor(
      project: string,
      token: string,
      opts: { signalwireSpaceUrl: string }
    );
    incomingPhoneNumbers: IncomingPhoneNumbersResource;
    messages: MessagesResource;
    calls: CallsResource;
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
