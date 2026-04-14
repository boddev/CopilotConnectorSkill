// Declarative Agent with a Copilot Connector as a knowledge source
//
// This TypeSpec file defines a Declarative Agent that uses a Copilot Connector
// to answer questions about Contoso Helpdesk tickets. The agent references the
// connector by its connection ID ("contosohelpdesk"), which must match the ID
// used when creating the connector (see connector-config.ts).
//
// Prerequisites:
//   - TypeSpec compiler with @microsoft/typespec-m365-copilot package
//   - A deployed Copilot Connector with connection ID "contosohelpdesk"
//   - Items ingested and inline results enabled
//
// Compile: tsp compile .
//
// Learn more:
//   https://learn.microsoft.com/microsoft-365/copilot/extensibility/overview-declarative-agent

import "@typespec/http";
import "@microsoft/typespec-m365-copilot";

using TypeSpec.Http;
using TypeSpec.M365.Copilot.Agents;

// ---------------------------------------------------------------------------
// Agent definition
// ---------------------------------------------------------------------------

@agent(
  "Helpdesk Assistant",
  "An AI assistant that helps employees find, track, and resolve IT helpdesk tickets from the Contoso Helpdesk system."
)
@instructions("""
  You are the Contoso Helpdesk Assistant. Your role is to help employees find
  relevant helpdesk tickets, understand their status, and provide resolution
  guidance based on past incidents.

  Guidelines:
  - Always search the helpdesk connector for relevant tickets before answering.
  - When reporting ticket information, include the ticket ID, title, status,
    priority, and assignee.
  - Provide resolution steps or workarounds when available.
  - Look for the most recent tickets first — prefer recent data over old.
  - When reporting counts of tickets, always note that the results may be a
    subset of the total and should not be treated as exact totals.
  - If a user asks about a specific ticket by ID, use exact match search.
  - For aggregate questions (e.g., "how many open tickets"), look for
    pre-computed summary items first.
  - Always include citation links so users can navigate to the source ticket.
""")

// Conversation starters — shown to users as suggested prompts
@conversationStarter(#{
  title: "Recent open tickets",
  text: "What are the most recent open helpdesk tickets?"
})
@conversationStarter(#{
  title: "Find a ticket",
  text: "Find helpdesk tickets about VPN connection issues"
})
@conversationStarter(#{
  title: "Check ticket status",
  text: "What is the status of ticket TICKET-001?"
})
@conversationStarter(#{
  title: "Assigned tickets",
  text: "Show me all helpdesk tickets assigned to Jane Smith"
})

namespace HelpdeskAgent {

  // -------------------------------------------------------------------------
  // Capabilities: Connect the agent to the Copilot Connector
  // -------------------------------------------------------------------------

  /**
   * Reference the Copilot Connector as a knowledge source.
   *
   * The connectionId must match the ID used when creating the external
   * connection via the Microsoft Graph API or Agents Toolkit.
   *
   * You can reference multiple connectors by adding entries to the array:
   *
   *   Connections = [
   *     { connectionId: "contosohelpdesk" },
   *     { connectionId: "contosokb" },
   *   ]
   */
  op copilotConnectors is AgentCapabilities.GraphConnectors<
    Connections = [
      {
        connectionId: "contosohelpdesk",
      }
    ]
  >;
}
