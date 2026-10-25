import assert from "node:assert/strict";
import test from "node:test";

test("public campaign does not require a GrantFlow login", () => {
  const redirects: string[] = [];
  assert.equal(requireGrantFlowAuth({pathname:"/gfm-app/give/synthetic-campaign",location:{replace:path=>redirects.push(path)}}),false);
  assert.deepEqual(redirects,[]);
  assert.equal(requireGrantFlowAuth({pathname:"/gfm-app/applications",location:{replace:path=>redirects.push(path)}}),true);
});
import {
  GRANTFLOW_LOGIN_PATH,
  clearGrantFlowBrowserState,
  logoutGrantFlowClient,
  requireGrantFlowAuth,
  grantFlowLoginPath,
  hasGrantFlowToken,
} from "../lib/auth-session.ts";

class MemoryStorage {
  private store = new Map<string, string>();

  get length(): number {
    return this.store.size;
  }

  clear() {
    this.store.clear();
  }

  getItem(key: string): string | null {
    return this.store.has(key) ? this.store.get(key)! : null;
  }

  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null;
  }

  removeItem(key: string) {
    this.store.delete(key);
  }

  setItem(key: string, value: string) {
    this.store.set(key, value);
  }
}

test("logout clears GrantFlow token, app cache, and redirects to login", () => {
  const localStorage = new MemoryStorage();
  const sessionStorage = new MemoryStorage();
  const redirects: string[] = [];
  let queryCleared = false;

  localStorage.setItem("gfm_token", "token-123");
  localStorage.setItem("gfm_prompt", "draft");
  localStorage.setItem("unrelated", "keep-me");
  sessionStorage.setItem("gfm_cache", "cached");

  const path = logoutGrantFlowClient({
    localStorage,
    sessionStorage,
    queryClient: {
      clear() {
        queryCleared = true;
      },
    },
    location: {
      replace(nextPath: string) {
        redirects.push(nextPath);
      },
    },
  });

  assert.equal(path, GRANTFLOW_LOGIN_PATH);
  assert.equal(localStorage.getItem("gfm_token"), null);
  assert.equal(localStorage.getItem("gfm_prompt"), null);
  assert.equal(localStorage.getItem("unrelated"), "keep-me");
  assert.equal(sessionStorage.getItem("gfm_cache"), null);
  assert.equal(queryCleared, true);
  assert.deepEqual(redirects, [GRANTFLOW_LOGIN_PATH]);
});

test("protected routes redirect after logout clears auth state", () => {
  const localStorage = new MemoryStorage();
  const sessionStorage = new MemoryStorage();
  const redirects: string[] = [];

  localStorage.setItem("gfm_token", "token-123");
  clearGrantFlowBrowserState({ localStorage, sessionStorage });

  const redirected = requireGrantFlowAuth({
    pathname: "/dashboard",
    localStorage,
    location: {
      replace(nextPath: string) {
        redirects.push(nextPath);
      },
    },
  });

  assert.equal(redirected, true);
  assert.deepEqual(redirects, [GRANTFLOW_LOGIN_PATH]);
});

test('central token is used; old GFM token cannot authenticate', () => {
  const storage = new MemoryStorage();
  storage.setItem('gfm_token', 'old-token');
  assert.equal(hasGrantFlowToken(storage), false);
  storage.setItem('authToken', 'central-token');
  assert.equal(hasGrantFlowToken(storage), true);
});

test('login preserves requested app path and rejects unsafe destinations', () => {
  assert.equal(grantFlowLoginPath('/applications/12?tab=documents'), '/auth/login?next=%2Fgfm-app%2Fapplications%2F12%3Ftab%3Ddocuments');
  for (const path of ['//evil.test', '/\\evil.test', '/../admin']) {
    assert.equal(grantFlowLoginPath(path), GRANTFLOW_LOGIN_PATH);
  }
});
