import { useState } from "react";

import {
  SETTINGS_PAGES,
  providerCredentialCopy,
  type ApiActionCredentialKind,
  type ApiProviderDescriptor,
  type ApiProviderId,
  type SettingsPageId
} from "./workspaceTypes";

export function ProviderSettingsPanel({
  providerList,
  selectedAiProvider,
  selectedAiProviderId,
  selectedProviderStatus,
  selectedProviderHasSavedKey,
  providerApiKey,
  saveProviderPending,
  clearProviderPending,
  llmEnabled,
  autoCommitThreshold,
  updateSettingsPending,
  onProviderChange,
  onProviderApiKeyChange,
  onSaveProviderKey,
  onClearProviderKey,
  onLlmEnabledChange,
  onAutoCommitThresholdChange,
  onSaveSettings
}: {
  providerList: ApiProviderDescriptor[];
  selectedAiProvider?: ApiProviderDescriptor;
  selectedAiProviderId: ApiProviderId;
  selectedProviderStatus: string;
  selectedProviderHasSavedKey: boolean;
  providerApiKey: string;
  saveProviderPending: boolean;
  clearProviderPending: boolean;
  llmEnabled: boolean;
  autoCommitThreshold: number;
  updateSettingsPending: boolean;
  onProviderChange: (providerId: ApiProviderId) => void;
  onProviderApiKeyChange: (value: string) => void;
  onSaveProviderKey: () => void;
  onClearProviderKey: () => void;
  onLlmEnabledChange: (enabled: boolean) => void;
  onAutoCommitThresholdChange: (threshold: number) => void;
  onSaveSettings: () => void;
}) {
  return (
    <div className="provider-settings" aria-label="AI provider credentials">
      <div className="provider-settings-head">
        <span>AI provider</span>
        <strong>{selectedProviderStatus}</strong>
      </div>
      <label>
        Default provider
        <select value={selectedAiProviderId} onChange={(event) => onProviderChange(event.target.value as ApiProviderId)}>
          {providerList.map((provider) => (
            <option value={provider.id} key={provider.id}>
              {provider.label}
            </option>
          ))}
        </select>
      </label>
      {selectedAiProviderId !== "graphview-local" && (
        <>
          <label>
            API key
            <input
              type="password"
              value={providerApiKey}
              autoComplete="off"
              placeholder={selectedAiProvider?.configured ? "Configured" : "Provider key"}
              onChange={(event) => onProviderApiKeyChange(event.target.value)}
            />
          </label>
          <div className="provider-actions">
            <button type="button" disabled={saveProviderPending || !providerApiKey.trim()} onClick={onSaveProviderKey}>
              Save key
            </button>
            <button type="button" disabled={clearProviderPending || !selectedProviderHasSavedKey} onClick={onClearProviderKey}>
              Clear
            </button>
          </div>
        </>
      )}
      <div className="connector-settings" aria-label="Advanced connector settings">
        <label>
          <input type="checkbox" checked={llmEnabled} onChange={(event) => onLlmEnabledChange(event.target.checked)} />
          LLM extraction
        </label>
        <label>
          Auto-commit
          <input
            type="number"
            min="0"
            max="1"
            step="0.01"
            value={autoCommitThreshold}
            onChange={(event) => onAutoCommitThresholdChange(Number(event.target.value))}
          />
        </label>
      </div>
      <button className="provider-save-settings" type="button" disabled={updateSettingsPending} onClick={onSaveSettings}>
        Save settings
      </button>
    </div>
  );
}


export function SettingsWorkspace({
  providerList,
  selectedAiProvider,
  selectedAiProviderId,
  selectedProviderStatus,
  selectedProviderHasSavedKey,
  providerApiKey,
  saveProviderPending,
  clearProviderPending,
  llmEnabled,
  autoCommitThreshold,
  updateSettingsPending,
  onProviderChange,
  onProviderApiKeyChange,
  onSaveProviderKey,
  onClearProviderKey,
  actionCredentialStatus,
  actionCredentialPending,
  onSaveActionCredential,
  onClearActionCredential,
  onLlmEnabledChange,
  onAutoCommitThresholdChange,
  onSaveSettings
}: {
  providerList: ApiProviderDescriptor[];
  selectedAiProvider?: ApiProviderDescriptor;
  selectedAiProviderId: ApiProviderId;
  selectedProviderStatus: string;
  selectedProviderHasSavedKey: boolean;
  providerApiKey: string;
  saveProviderPending: boolean;
  clearProviderPending: boolean;
  llmEnabled: boolean;
  autoCommitThreshold: number;
  updateSettingsPending: boolean;
  onProviderChange: (providerId: ApiProviderId) => void;
  onProviderApiKeyChange: (value: string) => void;
  onSaveProviderKey: () => void;
  onClearProviderKey: () => void;
  actionCredentialStatus: Record<ApiActionCredentialKind, boolean>;
  actionCredentialPending?: ApiActionCredentialKind;
  onSaveActionCredential: (kind: ApiActionCredentialKind, credentials: Record<string, string>) => void;
  onClearActionCredential: (kind: ApiActionCredentialKind) => void;
  onLlmEnabledChange: (enabled: boolean) => void;
  onAutoCommitThresholdChange: (threshold: number) => void;
  onSaveSettings: () => void;
}) {
  const [activeSettingsPage, setActiveSettingsPage] = useState<SettingsPageId>("providers");
  const activePage = SETTINGS_PAGES.find((page) => page.id === activeSettingsPage) ?? SETTINGS_PAGES[0];
  const enabledProviders = providerList.filter((provider) => provider.enabled).length;
  const selectedModel = selectedAiProvider?.default_model ?? "graphview-local-deterministic-v1";
  const selectedCapabilities = selectedAiProvider?.capabilities ?? ["planning", "graph query", "research"];

  return (
    <section className="settings-workspace" aria-label="Settings">
      <aside className="settings-sidebar" aria-label="Settings navigation">
        <div>
          <p className="eyebrow">Settings</p>
          <strong>Workspace</strong>
          <span>Providers, credentials, automation, and runtime defaults.</span>
        </div>
        <nav className="settings-nav" role="tablist" aria-label="Settings pages">
          {SETTINGS_PAGES.map((page) => (
            <button
              type="button"
              role="tab"
              aria-selected={page.id === activeSettingsPage}
              key={page.id}
              onClick={() => setActiveSettingsPage(page.id)}
            >
              <strong>{page.label}</strong>
              <span>{page.summary}</span>
            </button>
          ))}
        </nav>
        <div className="settings-sidebar-status" aria-label="Settings status">
          <SettingsStat label="Default" value={selectedAiProvider?.label ?? "Graphview Local"} />
          <SettingsStat label="Enabled" value={enabledProviders.toString()} />
        </div>
      </aside>

      <div className="settings-page-main">
        <div className="settings-page-head">
          <div>
            <p className="eyebrow">Settings / {activePage.label}</p>
            <h2>{activePage.label}</h2>
            <span>{activePage.summary}</span>
          </div>
          <div className="settings-stat-strip" aria-label="Provider settings status">
            <SettingsStat label="Provider" value={selectedAiProvider?.label ?? "Graphview Local"} />
            <SettingsStat label="Credential" value={selectedProviderStatus} />
            <SettingsStat label="Extraction" value={llmEnabled ? "On" : "Off"} />
          </div>
        </div>

        <div className="settings-page-body">
          {activeSettingsPage === "providers" && (
            <section className="settings-section settings-provider-section" aria-label="Provider catalog">
              <div className="settings-section-head">
                <div>
                  <p className="eyebrow">Providers</p>
                  <h3>Model routing</h3>
                </div>
                <span className="settings-status-pill">{selectedProviderStatus}</span>
              </div>
              <div className="settings-provider-grid">
                {providerList.map((provider) => (
                  <button
                    className="provider-status-card"
                    type="button"
                    aria-pressed={provider.id === selectedAiProviderId}
                    key={provider.id}
                    onClick={() => onProviderChange(provider.id)}
                  >
                    <span className={provider.enabled ? "is-enabled" : ""}>{provider.enabled ? "Enabled" : "Not configured"}</span>
                    <strong>{provider.label}</strong>
                    <small>{provider.default_model}</small>
                  </button>
                ))}
              </div>
            </section>
          )}

          {activeSettingsPage === "credentials" && (
            <section className="settings-section settings-form-section" aria-label="Provider credentials">
              <div className="settings-section-head">
                <div>
                  <p className="eyebrow">Credentials</p>
                  <h3>Provider access</h3>
                </div>
                <span className="settings-status-pill">{selectedProviderStatus}</span>
              </div>
              <ProviderCredentialPanel
                providerList={providerList}
                selectedAiProvider={selectedAiProvider}
                selectedAiProviderId={selectedAiProviderId}
                selectedProviderHasSavedKey={selectedProviderHasSavedKey}
                providerApiKey={providerApiKey}
                saveProviderPending={saveProviderPending}
                clearProviderPending={clearProviderPending}
                onProviderChange={onProviderChange}
                onProviderApiKeyChange={onProviderApiKeyChange}
                onSaveProviderKey={onSaveProviderKey}
                onClearProviderKey={onClearProviderKey}
              />
              <ActionCredentialPanel
                status={actionCredentialStatus}
                pending={actionCredentialPending}
                onSave={onSaveActionCredential}
                onClear={onClearActionCredential}
              />
            </section>
          )}

          {activeSettingsPage === "automation" && (
            <section className="settings-section settings-form-section" aria-label="Automation settings">
              <div className="settings-section-head">
                <div>
                  <p className="eyebrow">Automation</p>
                  <h3>Extraction and review rules</h3>
                </div>
              </div>
              <AutomationSettingsPanel
                llmEnabled={llmEnabled}
                autoCommitThreshold={autoCommitThreshold}
                updateSettingsPending={updateSettingsPending}
                onLlmEnabledChange={onLlmEnabledChange}
                onAutoCommitThresholdChange={onAutoCommitThresholdChange}
                onSaveSettings={onSaveSettings}
              />
            </section>
          )}

          {activeSettingsPage === "runtime" && (
            <section className="settings-section settings-runtime-section" aria-label="Runtime defaults">
              <div className="settings-section-head">
                <div>
                  <p className="eyebrow">Runtime</p>
                  <h3>Defaults and guardrails</h3>
                </div>
              </div>
              <div className="settings-readout-grid">
                <SettingsReadout label="Runtime model" value={selectedModel} detail="Used for planning, graph Q&A, and research runs." />
                <SettingsReadout label="Credential source" value={selectedProviderStatus} detail="Reflects saved provider credential state." />
                <SettingsReadout label="Auto-commit" value={autoCommitThreshold.toFixed(2)} detail="Minimum confidence before automatic graph commits." />
                <SettingsReadout label="Extraction" value={llmEnabled ? "LLM-assisted" : "Deterministic"} detail="Controls connector and ingestion proposal generation." />
              </div>
            </section>
          )}

          {activeSettingsPage === "capabilities" && (
            <section className="settings-section settings-capability-section" aria-label="Selected provider capabilities">
              <div className="settings-section-head">
                <div>
                  <p className="eyebrow">Capabilities</p>
                  <h3>{selectedAiProvider?.label ?? "Graphview Local"}</h3>
                </div>
              </div>
              <div className="settings-capability-list">
                {selectedCapabilities.map((capability) => (
                  <span key={capability}>{capability.replaceAll("_", " ")}</span>
                ))}
              </div>
              <div className="settings-provider-matrix">
                {providerList.map((provider) => (
                  <article key={provider.id}>
                    <span>{provider.enabled ? "Enabled" : "Needs setup"}</span>
                    <strong>{provider.label}</strong>
                    <small>{provider.capabilities.map((capability) => capability.replaceAll("_", " ")).join(" / ")}</small>
                  </article>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>
    </section>
  );
}

function ActionCredentialPanel({
  status,
  pending,
  onSave,
  onClear
}: {
  status: Record<ApiActionCredentialKind, boolean>;
  pending?: ApiActionCredentialKind;
  onSave: (kind: ApiActionCredentialKind, credentials: Record<string, string>) => void;
  onClear: (kind: ApiActionCredentialKind) => void;
}) {
  const [activeKind, setActiveKind] = useState<ApiActionCredentialKind>("github");
  const [primarySecret, setPrimarySecret] = useState("");
  const [secondarySecret, setSecondarySecret] = useState("");
  const [username, setUsername] = useState("");
  const labels: Record<ApiActionCredentialKind, { title: string; primary: string; secondary?: string }> = {
    github: { title: "GitHub Issues", primary: "Installation or access token" },
    smtp: { title: "SMTP relay", primary: "Password", secondary: "Username" },
    webhook: { title: "Signed webhook", primary: "Signing secret", secondary: "Callback secret" }
  };
  const selected = labels[activeKind];
  const save = () => {
    let credentials: Record<string, string>;
    if (activeKind === "github") credentials = { token: primarySecret };
    else if (activeKind === "smtp") credentials = username ? { username, password: primarySecret } : {};
    else credentials = { secret: primarySecret, callback_secret: secondarySecret || primarySecret };
    onSave(activeKind, credentials);
    setPrimarySecret("");
    setSecondarySecret("");
    setUsername("");
  };

  return (
    <div className="credential-settings-grid" aria-label="External action credentials">
      <div className="credential-provider-grid">
        {(Object.keys(labels) as ApiActionCredentialKind[]).map((kind) => (
          <button
            className="credential-provider-card"
            type="button"
            aria-pressed={kind === activeKind}
            key={kind}
            onClick={() => {
              setActiveKind(kind);
              setPrimarySecret("");
              setSecondarySecret("");
              setUsername("");
            }}
          >
            <span className={status[kind] ? "is-configured" : ""}>{status[kind] ? "Configured" : "Needs setup"}</span>
            <strong>{labels[kind].title}</strong>
            <small>Worker-only secret resolution</small>
          </button>
        ))}
      </div>
      <div className="credential-detail-panel">
        <div className="credential-detail-head">
          <div>
            <p className="eyebrow">External actions</p>
            <h4>{selected.title}</h4>
            <span>Secrets are stored externally and never copied into reviewed proposals.</span>
          </div>
          <strong>{status[activeKind] ? "Configured" : "Not configured"}</strong>
        </div>
        <div className="credential-key-panel">
          {selected.secondary && activeKind === "smtp" && (
            <label>
              {selected.secondary}
              <input type="text" value={username} autoComplete="off" onChange={(event) => setUsername(event.target.value)} />
            </label>
          )}
          <label>
            {selected.primary}
            <input
              type="password"
              value={primarySecret}
              autoComplete="off"
              placeholder={status[activeKind] ? "Configured" : selected.primary}
              onChange={(event) => setPrimarySecret(event.target.value)}
            />
          </label>
          {selected.secondary && activeKind === "webhook" && (
            <label>
              {selected.secondary}
              <input
                type="password"
                value={secondarySecret}
                autoComplete="off"
                placeholder="Defaults to signing secret"
                onChange={(event) => setSecondarySecret(event.target.value)}
              />
            </label>
          )}
          <div className="credential-key-actions">
            <button
              className="provider-save-settings"
              type="button"
              disabled={pending === activeKind || (activeKind !== "smtp" && !primarySecret.trim()) || (activeKind === "smtp" && Boolean(username) !== Boolean(primarySecret))}
              onClick={save}
            >
              Save credential
            </button>
            <button type="button" disabled={pending === activeKind || !status[activeKind]} onClick={() => onClear(activeKind)}>
              Clear credential
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function ProviderCredentialPanel({
  providerList,
  selectedAiProvider,
  selectedAiProviderId,
  selectedProviderHasSavedKey,
  providerApiKey,
  saveProviderPending,
  clearProviderPending,
  onProviderChange,
  onProviderApiKeyChange,
  onSaveProviderKey,
  onClearProviderKey
}: {
  providerList: ApiProviderDescriptor[];
  selectedAiProvider?: ApiProviderDescriptor;
  selectedAiProviderId: ApiProviderId;
  selectedProviderHasSavedKey: boolean;
  providerApiKey: string;
  saveProviderPending: boolean;
  clearProviderPending: boolean;
  onProviderChange: (providerId: ApiProviderId) => void;
  onProviderApiKeyChange: (value: string) => void;
  onSaveProviderKey: () => void;
  onClearProviderKey: () => void;
}) {
  const selectedCredentialStatus =
    selectedAiProviderId === "graphview-local"
      ? "No key required"
      : selectedProviderHasSavedKey
        ? "Saved key"
        : selectedAiProvider?.configured
          ? "Environment key"
          : "Needs key";
  const credentialCopy = providerCredentialCopy[selectedAiProviderId];
  const selectedModels =
    selectedAiProvider?.models?.length
      ? selectedAiProvider.models
      : [
          {
            id: selectedAiProvider?.default_model ?? "graphview-local-deterministic-v1",
            label: selectedAiProvider?.default_model ?? "graphview-local-deterministic-v1",
            default: true,
            capabilities: selectedAiProvider?.capabilities ?? []
          }
        ];
  const selectedDefaultModel = selectedModels.find((model) => model.default) ?? selectedModels[0];

  return (
    <div className="credential-settings-grid">
      <div className="credential-provider-grid" aria-label="LLM provider selection">
        {providerList.map((provider) => {
          const providerStatus = provider.id === "graphview-local" ? "No key" : provider.configured ? "Configured" : "Needs key";
          return (
            <button
              className="credential-provider-card"
              type="button"
              aria-pressed={provider.id === selectedAiProviderId}
              key={provider.id}
              onClick={() => onProviderChange(provider.id)}
            >
              <span className={provider.configured ? "is-configured" : ""}>{providerStatus}</span>
              <strong>{provider.label}</strong>
              <small>{provider.default_model}</small>
            </button>
          );
        })}
      </div>

      <div className="credential-detail-panel">
        <div className="credential-detail-head">
          <div>
            <p className="eyebrow">Selected provider</p>
            <h4>{selectedAiProvider?.label ?? "Graphview Local"}</h4>
            <span>{credentialCopy.detail}</span>
          </div>
          <strong>{selectedCredentialStatus}</strong>
        </div>

        <div className="credential-summary-row" aria-label="Selected provider details">
          <div>
            <span>Default model</span>
            <strong>{selectedDefaultModel.label}</strong>
          </div>
          <div>
            <span>Credential source</span>
            <strong>{credentialCopy.source}</strong>
          </div>
        </div>

        <div className="credential-model-list" aria-label={`${selectedAiProvider?.label ?? "Provider"} model catalog`}>
          {selectedModels.map((model) => (
            <span key={model.id}>
              <strong>{model.label}</strong>
              <small>{model.default ? "Default" : model.capabilities.map((capability) => capability.replaceAll("_", " ")).join(" / ")}</small>
            </span>
          ))}
        </div>

        {selectedAiProviderId === "graphview-local" ? (
          <div className="settings-callout credential-callout">
            <strong>Graphview Local</strong>
            <span>Runs without external credentials and remains available when cloud providers are not configured.</span>
          </div>
        ) : (
          <div className="credential-key-panel">
            <label>
              {credentialCopy.secretLabel}
              <input
                type="password"
                value={providerApiKey}
                autoComplete="off"
                aria-label={credentialCopy.secretLabel}
                placeholder={selectedAiProvider?.configured ? `${selectedAiProvider.label} key configured` : credentialCopy.placeholder}
                onChange={(event) => onProviderApiKeyChange(event.target.value)}
              />
            </label>
            <div className="credential-key-actions">
              <button className="provider-save-settings" type="button" disabled={saveProviderPending || !providerApiKey.trim()} onClick={onSaveProviderKey}>
                Save key
              </button>
              <button type="button" disabled={clearProviderPending || !selectedProviderHasSavedKey} onClick={onClearProviderKey}>
                Clear key
              </button>
            </div>
            <small>Saving sets {selectedAiProvider?.label ?? "this provider"} as the default LLM provider.</small>
          </div>
        )}
      </div>
    </div>
  );
}

function AutomationSettingsPanel({
  llmEnabled,
  autoCommitThreshold,
  updateSettingsPending,
  onLlmEnabledChange,
  onAutoCommitThresholdChange,
  onSaveSettings
}: {
  llmEnabled: boolean;
  autoCommitThreshold: number;
  updateSettingsPending: boolean;
  onLlmEnabledChange: (enabled: boolean) => void;
  onAutoCommitThresholdChange: (threshold: number) => void;
  onSaveSettings: () => void;
}) {
  return (
    <div className="settings-form-grid">
      <label className="settings-toggle-row">
        <input type="checkbox" checked={llmEnabled} onChange={(event) => onLlmEnabledChange(event.target.checked)} />
        <span>
          <strong>LLM extraction</strong>
          <small>Use the selected provider to generate richer graph proposals during ingestion.</small>
        </span>
      </label>
      <label>
        Auto-commit threshold
        <input
          type="number"
          min="0"
          max="1"
          step="0.01"
          value={autoCommitThreshold}
          onChange={(event) => onAutoCommitThresholdChange(Number(event.target.value))}
        />
      </label>
      <button className="provider-save-settings" type="button" disabled={updateSettingsPending} onClick={onSaveSettings}>
        Save automation
      </button>
    </div>
  );
}

function SettingsStat({ label, value }: { label: string; value: string }) {
  return (
    <span>
      <strong>{value}</strong>
      {label}
    </span>
  );
}

function SettingsReadout({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}
