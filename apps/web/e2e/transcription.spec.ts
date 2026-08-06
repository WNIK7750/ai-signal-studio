import { expect, test } from "@playwright/test";

declare global {
  interface Window {
    __sttTrackStopped: boolean;
  }
}

test("realtime transcription appends final text but never sends it", async ({
  page,
}) => {
  const installFakes = () => {
    window.__sttTrackStopped = false;
    const track = {
      stop: () => {
        window.__sttTrackStopped = true;
      },
    };
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: async () => ({
          getTracks: () => [track],
        }),
      },
    });

    class FakeMediaRecorder {
      static isTypeSupported() {
        return true;
      }
      state = "inactive";
      ondataavailable:
        | ((event: { data: Blob }) => void | Promise<void>)
        | null = null;
      constructor(public stream: MediaStream) {}
      start() {
        this.state = "recording";
        setTimeout(() => {
          void this.ondataavailable?.({
            data: new Blob(["fake-audio"], { type: "audio/webm" }),
          });
        }, 20);
      }
      stop() {
        this.state = "inactive";
      }
    }
    Object.defineProperty(window, "MediaRecorder", {
      configurable: true,
      value: FakeMediaRecorder,
    });

    class FakeWebSocket {
      static OPEN = 1;
      readyState = FakeWebSocket.OPEN;
      onopen: (() => void) | null = null;
      onmessage: ((event: { data: string }) => void) | null = null;
      onerror: (() => void) | null = null;
      onclose: (() => void) | null = null;
      constructor(public url: string) {
        queueMicrotask(() => this.onopen?.());
      }
      send(data: string | ArrayBuffer) {
        if (typeof data === "string") {
          const message = JSON.parse(data);
          if (message.type === "stop") {
            this.onmessage?.({
              data: JSON.stringify({
                type: "session.closed",
                session_id: "stt_e2e",
                final_text: "最终转写文字",
              }),
            });
          }
          return;
        }
        this.onmessage?.({
          data: JSON.stringify({
            type: "transcript.partial",
            session_id: "stt_e2e",
            segment_id: "segment_1",
            revision: 1,
            text: "最终转写",
          }),
        });
        this.onmessage?.({
          data: JSON.stringify({
            type: "transcript.final",
            session_id: "stt_e2e",
            segment_id: "segment_1",
            revision: 2,
            text: "最终转写文字",
          }),
        });
      }
      close() {
        this.readyState = 3;
        this.onclose?.();
      }
    }
    Object.defineProperty(window, "WebSocket", {
      configurable: true,
      value: FakeWebSocket,
    });
  };
  await page.route("**/api/transcription/sessions", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        session_id: "stt_e2e",
        status: "created",
        provider: "fake",
        language: "zh",
        format: "webm_opus",
        sample_rate: 48000,
        final_text: "",
        error_code: null,
        websocket_url: "/ws/transcription/stt_e2e",
        token: "short-lived-test-token",
      }),
    });
  });

  await page.goto("/agent");
  const composer = page.getByPlaceholder("向 Workspace Agent 发送消息…");
  await expect(composer).toBeEnabled();
  await page.evaluate(installFakes);
  const messageCount = await page.locator(".message").count();
  await page.getByRole("button", { name: "语音转文字" }).click();
  await expect(composer).toHaveValue("最终转写文字");
  await expect(page.locator(".message")).toHaveCount(messageCount);

  await page.getByRole("button", { name: "停止语音转文字" }).click();
  await expect
    .poll(() => page.evaluate(() => window.__sttTrackStopped))
    .toBe(true);
  await expect(composer).toHaveValue("最终转写文字");
  await expect(page.locator(".message")).toHaveCount(messageCount);
});
