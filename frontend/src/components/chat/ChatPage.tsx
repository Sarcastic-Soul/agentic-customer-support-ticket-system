import { useState } from "react";
import { clearCustomer, getStoredCustomer, type CustomerSession } from "../../lib/customer";
import { ChatWindow } from "./ChatWindow";
import { EmailGate } from "./EmailGate";

export function ChatPage() {
  const [customer, setCustomer] = useState<CustomerSession | null>(getStoredCustomer);

  if (!customer) {
    return <EmailGate onLogin={setCustomer} />;
  }

  return (
    <ChatWindow
      customer={customer}
      onSwitchUser={() => {
        clearCustomer();
        setCustomer(null);
      }}
    />
  );
}
