import { readFileSync } from "node:fs";
import { isAbsolute, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { cert, initializeApp, deleteApp } from "firebase-admin/app";
import { getAuth } from "firebase-admin/auth";

const projectRoot = fileURLToPath(new URL("../", import.meta.url));

// check firebase settings without changing anything.
let app;

try {
  const projectId = process.env.FIREBASE_PROJECT_ID;
  const rawKeyPath = process.env.FIREBASE_ADMIN_KEY_PATH;

  if (!projectId || !rawKeyPath) {
    throw new Error("Missing project ID or key path");
  }

  const keyPath = isAbsolute(rawKeyPath) ? rawKeyPath : resolve(projectRoot, rawKeyPath);

  // read the private key file on this computer.
  const key = JSON.parse(readFileSync(keyPath, "utf8"));

  if (key.project_id !== projectId) {
    throw new Error("The key belongs to a different project");
  }

  app = initializeApp({
    credential: cert(key),
    projectId,
  });

  // ask firebase for the current authenticator settings.
  const config = await getAuth(app).projectConfigManager().getProjectConfig();

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
    // close the local connection without deleting the project.
    await deleteApp(app);
  }
}
