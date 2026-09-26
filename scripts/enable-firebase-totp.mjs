import { readFileSync } from "node:fs";
import { cert, initializeApp, deleteApp } from "firebase-admin/app";
import { getAuth } from "firebase-admin/auth";

let app;

try {
  const projectId = process.env.FIREBASE_PROJECT_ID;
  const keyPath = process.env.FIREBASE_ADMIN_KEY_PATH;

  if (!projectId || !keyPath) {
    throw new Error("Missing project ID or key path");
  }

  const key = JSON.parse(readFileSync(keyPath, "utf8"));

  if (key.project_id !== projectId) {
    throw new Error("The key belongs to a different project");
  }

  app = initializeApp({
    credential: cert(key),
    projectId,
  });

  const manager = getAuth(app).projectConfigManager();
  const current = await manager.getProjectConfig();

  const otherProviders = (
    current.multiFactorConfig?.providerConfigs ?? []
  ).filter((provider) => !provider.totpProviderConfig);

  await manager.updateProjectConfig({
    multiFactorConfig: {
      providerConfigs: [
        ...otherProviders,
        {
          state: "ENABLED",
          totpProviderConfig: {
            adjacentIntervals: 1,
          },
        },
      ],
    },
  });

  const config = await manager.getProjectConfig();

  const providers = config.multiFactorConfig?.providerConfigs ?? [];
  const totp = providers.find((provider) => provider.totpProviderConfig);

  console.log("Project:", projectId);
  console.log("TOTP state:", totp?.state ?? "NOT CONFIGURED");
} catch (error) {
  console.error("Configuration check failed.");
  console.error("Error code:", error.code ?? "local-setup-error");
  process.exitCode = 1;
} finally {
  if (app) {
    await deleteApp(app);
  }
}
