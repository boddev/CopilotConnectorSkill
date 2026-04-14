// Incremental sync pattern: track changes and only re-ingest modified items
// Shows: timestamp-based incremental sync with checkpoint tracking,
//   hash-based change detection using Node.js crypto module
//
// Prerequisites: npm install @microsoft/microsoft-graph-client @azure/identity

import { createHash } from "node:crypto";
import { Client } from "@microsoft/microsoft-graph-client";

/** A source item from the external data store. */
interface SourceItem {
  id: string;
  title: string;
  status: string;
  fullContent: string;
  url: string;
  iconUrl?: string;
  lastModified: Date;
}

/** Checkpoint persisted between sync runs. */
interface SyncCheckpoint {
  timestamp: Date;
  knownItemIds: Set<string>;
}

/** ACL entry for items. */
interface AclEntry {
  type: string;
  value: string;
  accessType: string;
}

/** An external item payload. */
interface ExternalItem {
  acl: AclEntry[];
  properties: Record<string, unknown>;
  content: {
    value: string;
    type: "text" | "html";
  };
}

/**
 * Performs incremental sync between an external data source
 * and a Microsoft Graph external connection.
 */
class IncrementalSync {
  constructor(
    private readonly graphClient: Client,
    private readonly connectionId: string
  ) {}

  /**
   * Perform incremental sync by comparing source items against a checkpoint.
   * Only ingests new/modified items and deletes removed items.
   *
   * @param currentSourceItems - All items currently in the source system
   * @param lastCheckpoint - Checkpoint from the previous sync run
   */
  async runIncrementalSync(
    currentSourceItems: SourceItem[],
    lastCheckpoint: SyncCheckpoint
  ): Promise<void> {
    const sourceById = new Map(
      currentSourceItems.map((item) => [item.id, item])
    );

    // 1. Find new and modified items
    const toUpsert = currentSourceItems.filter(
      (item) =>
        !lastCheckpoint.knownItemIds.has(item.id) ||
        item.lastModified > lastCheckpoint.timestamp
    );

    // 2. Find deleted items (in previous checkpoint but not in current source)
    const toDelete = [...lastCheckpoint.knownItemIds].filter(
      (id) => !sourceById.has(id)
    );

    console.log(
      `Incremental sync: ${toUpsert.length} upserts, ${toDelete.length} deletes`
    );

    // 3. Upsert new/modified items
    for (const sourceItem of toUpsert) {
      const externalItem = mapToExternalItem(sourceItem);
      await this.graphClient
        .api(
          `/external/connections/${this.connectionId}/items/${sourceItem.id}`
        )
        .put(externalItem);
    }

    // 4. Delete removed items
    for (const itemId of toDelete) {
      try {
        await this.graphClient
          .api(
            `/external/connections/${this.connectionId}/items/${itemId}`
          )
          .delete();
      } catch (error: unknown) {
        const statusCode = (error as { statusCode?: number }).statusCode;
        if (statusCode !== 404) throw error;
        // Item already deleted — safe to ignore
      }
    }

    // 5. Update checkpoint
    const newCheckpoint: SyncCheckpoint = {
      timestamp: new Date(),
      knownItemIds: new Set(sourceById.keys()),
    };
    await this.saveCheckpoint(newCheckpoint);
  }

  /**
   * Hash-based change detection: only re-ingest items whose content hash changed.
   * More efficient than timestamp-based when source doesn't track modification dates.
   *
   * @param currentSourceItems - All items currently in the source system
   * @param previousHashes - Map of item ID → content hash from previous run
   * @returns Updated hash map to persist for the next run
   */
  async runHashBasedSync(
    currentSourceItems: SourceItem[],
    previousHashes: Map<string, string>
  ): Promise<Map<string, string>> {
    const updatedHashes = new Map(previousHashes);

    for (const sourceItem of currentSourceItems) {
      const currentHash = computeContentHash(sourceItem);

      if (previousHashes.get(sourceItem.id) === currentHash) {
        continue; // No changes — skip
      }

      const externalItem = mapToExternalItem(sourceItem);
      await this.graphClient
        .api(
          `/external/connections/${this.connectionId}/items/${sourceItem.id}`
        )
        .put(externalItem);

      updatedHashes.set(sourceItem.id, currentHash);
    }

    return updatedHashes;
  }

  /**
   * Persist a checkpoint for the next sync run.
   * Implement: save to database, blob storage, or local file.
   */
  private async saveCheckpoint(checkpoint: SyncCheckpoint): Promise<void> {
    console.log(
      `Checkpoint saved: ${checkpoint.timestamp.toISOString()}, ` +
        `${checkpoint.knownItemIds.size} items`
    );
    // Replace with your persistence mechanism (e.g., fs, database, blob)
  }
}

/** Map a source item to a Graph external item payload. */
function mapToExternalItem(source: SourceItem): ExternalItem {
  return {
    acl: [
      {
        type: "everyone",
        value: "everyone",
        accessType: "grant",
      },
    ],
    properties: {
      title: source.title,
      status: source.status,
      lastModifiedDate: source.lastModified.toISOString(),
      itemUrl: source.url,
      iconUrl: source.iconUrl ?? "",
    },
    content: {
      value: source.fullContent,
      type: "text",
    },
  };
}

/** Compute a SHA-256 hash of an item's key fields for change detection. */
function computeContentHash(item: SourceItem): string {
  const combined = [
    item.title,
    item.status,
    item.fullContent,
    item.lastModified.toISOString(),
  ].join("|");

  return createHash("sha256").update(combined, "utf-8").digest("hex");
}

export {
  IncrementalSync,
  computeContentHash,
  mapToExternalItem,
  SourceItem,
  SyncCheckpoint,
  ExternalItem,
};
