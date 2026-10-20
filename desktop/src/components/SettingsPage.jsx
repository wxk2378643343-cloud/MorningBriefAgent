import React, { useState } from "react";
import { ChevronRight, Sparkles } from "lucide-react";
import { fetchJson } from "../localApi";
import { ONBOARDING_STEPS } from "./onboarding/OnboardingScreen";

export default function SettingsPage({ profile, status, onOpenSetup, onProfileUpdated, onReconfigure }) {
  const [selectedKey, setSelectedKey] = useState("workspace");
  const [displayName, setDisplayName] = useState(profile?.display_name ?? "");
  const [profileMessage, setProfileMessage] = useState("");
  const selectedStep = ONBOARDING_STEPS.find((step) => step.key === selectedKey) ?? ONBOARDING_STEPS[0];
  const SelectedIcon = selectedStep.icon;
  const selectedState = status?.steps?.find((item) => item.step_key === selectedStep.key)?.status ?? "pending";
  const stateLabel = { completed: "已连接", skipped: "稍后配置", pending: "未配置" }[selectedState] ?? "未配置";
  const stateTone = { completed: "success", skipped: "muted", pending: "warning" }[selectedState] ?? "warning";
  const stepDescriptions = {
    workspace: "管理本地工作区、知识库文件和运行数据的位置。",
    provider: "选择本地 Agent 或 API，并管理模型连接方式。",
    channel: "配置飞书等消息渠道，让业务工作流可以主动通知你。",
    profile: "告诉 Agent 你的工作重点和当前目标，形成可编辑的本地记忆。",
  };
  const completed = status?.completed_count ?? 0;
  const skipped = status?.skipped_count ?? 0;
  const saveDisplayName = async () => {
    const normalizedName = displayName.trim();
    if (!normalizedName) {
      setProfileMessage("名字不能为空。");
      return;
    }
    try {
      const nextProfile = await fetchJson("/api/v1/profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ display_name: normalizedName }),
      });
      onProfileUpdated?.(nextProfile);
      setDisplayName(nextProfile.display_name);
      setProfileMessage("名字已保存。");
    } catch {
      setProfileMessage("名字保存失败。");
    }
  };

  return (
    <section className="settings-page mx-auto max-w-[1120px] !pt-2">
      <div className="settings-hero !items-center !border-0 !pb-8">
        <div>
          <span className="eyebrow !text-[10px] !tracking-[.18em]">LOCAL SETTINGS</span>
          <h2 className="!mt-3 !text-[36px] !font-semibold !tracking-[-.06em]">设置</h2>
          <p className="!mt-2 !text-[13px]">让本地 Agent 更贴合你的工作方式。</p>
        </div>
        <div className="settings-summary !min-w-[154px] !rounded-2xl !border-black/[.08] !bg-white/80 !shadow-[0_12px_40px_rgba(0,0,0,.06)]">
          <strong className="!text-[26px] !text-[#171717]">{completed}/{ONBOARDING_STEPS.length}</strong>
          <span>配置项已完成</span>
          {skipped > 0 && <small>{skipped} 项稍后配置</small>}
        </div>
      </div>
      <div className="settings-shell !grid-cols-[250px_minmax(0,1fr)] !rounded-[24px] !border-black/[.08] !shadow-[0_22px_70px_rgba(0,0,0,.07)]">
        <nav className="settings-nav !gap-1 !bg-[#fafafa] !p-3" aria-label="设置分类">
          <div className="settings-nav-title !px-3 !pb-3 !text-[10px]">设置</div>
          {ONBOARDING_STEPS.map((step) => {
            const Icon = step.icon;
            const stepState = status?.steps?.find((item) => item.step_key === step.key)?.status ?? "pending";
            return (
              <button
                type="button"
                className={`settings-nav-item !rounded-xl !px-3 !py-3 ${selectedKey === step.key ? "active !border-black/[.08] !bg-white !text-black !shadow-[0_4px_14px_rgba(0,0,0,.06)]" : "!text-[#737373]"}`}
                key={step.key}
                onClick={() => setSelectedKey(step.key)}
              >
                <span className={`settings-nav-icon !h-8 !w-8 !rounded-[10px] ${selectedKey === step.key ? "!bg-black !text-white" : "!bg-[#ededed] !text-[#737373]"}`}>
                  <Icon size={15} />
                </span>
                <span>
                  <strong className="!text-[12px]">{step.label}</strong>
                  <small>{stepState === "completed" ? "已连接" : stepState === "skipped" ? "稍后配置" : "未配置"}</small>
                </span>
                <ChevronRight size={14} />
              </button>
            );
          })}
          <div className="settings-nav-foot !text-[#a3a3a3]">
            <span className="local-dot !bg-black !shadow-none" />
            数据仅保存在本机
          </div>
        </nav>
        <div className="settings-detail !bg-white">
          <div className="settings-detail-head !gap-4 !border-black/[.06] !px-9 !py-8">
            <div className="settings-detail-icon settings-icon-float !h-12 !w-12 !rounded-2xl !bg-black !text-white">
              <SelectedIcon size={21} />
            </div>
            <div>
              <div className="settings-detail-title">
                <h3 className="!text-[21px] !font-semibold !tracking-[-.03em]">{selectedStep.label}</h3>
                <span className={`settings-status ${stateTone} !rounded-full !border !border-black/[.06]`}>{stateLabel}</span>
              </div>
              <p>{stepDescriptions[selectedStep.key]}</p>
            </div>
          </div>
          <div className="settings-detail-body !gap-6 !px-9 !py-8">
            {selectedKey === "profile" && (
              <div className="settings-state-row !rounded-2xl !border-black/[.08] !bg-white !p-5">
                <label className="settings-profile-name">
                  <strong>你的名字</strong>
                  <span>首页问候会使用这个名字。</span>
                  <input
                    value={displayName}
                    maxLength={40}
                    autoComplete="name"
                    onChange={(event) => {
                      setDisplayName(event.target.value);
                      setProfileMessage("");
                    }}
                  />
                </label>
                <button className="primary !rounded-full !bg-black !px-5 !py-3" type="button" onClick={saveDisplayName}>
                  保存名字
                </button>
                {profileMessage && <small className="settings-profile-message">{profileMessage}</small>}
              </div>
            )}
            <div className="settings-state-row settings-state-row-hover !rounded-2xl !border-black/[.08] !bg-[#fafafa] !p-5">
              <div>
                <strong className="!text-[14px]">
                  {selectedState === "completed" ? "配置已生效" : selectedState === "skipped" ? "这项配置可以稍后补充" : "这项配置还没有完成"}
                </strong>
                <span>{selectedState === "completed" ? "你可以随时进入向导修改。" : "进入配置向导完成后，状态会在这里更新。"}</span>
              </div>
              <button className="primary !rounded-full !bg-black !px-5 !py-3 hover:!bg-[#333]" type="button" onClick={() => onOpenSetup(selectedStep.key)}>
                {selectedState === "completed" ? "修改设置" : "开始配置"} <ChevronRight size={15} />
              </button>
            </div>
            <div className="settings-note !text-[#a3a3a3]">
              <Sparkles size={16} />
              <span>首次启动向导只负责建立基础配置；这里是日常修改入口。</span>
            </div>
          </div>
        </div>
      </div>
      <div className="settings-danger-zone !mt-5 !rounded-2xl !border-black/[.07] !bg-white/70">
        <div>
          <strong>重新运行初始化向导</strong>
          <p>保留本地文件，只重置配置进度。适合更换工作区或重新选择 Agent。</p>
        </div>
        <button className="secondary !rounded-full !border-black/[.1]" type="button" onClick={onReconfigure}>重新配置</button>
      </div>
    </section>
  );
}
