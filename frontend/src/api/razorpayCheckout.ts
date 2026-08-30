import type {
  RazorpayTestCheckoutOrder,
} from "./testCheckout";


const RAZORPAY_CHECKOUT_SCRIPT_URL = (
  "https://checkout.razorpay.com/v1/checkout.js"
);


type RazorpayCheckoutSuccess = {
  razorpay_payment_id: string;
  razorpay_order_id: string;
  razorpay_signature: string;
};


type RazorpayCheckoutFailure = {
  error?: {
    code?: string;
    description?: string;
    source?: string;
    step?: string;
    reason?: string;
    metadata?: {
      order_id?: string;
      payment_id?: string;
    };
  };
};


type RazorpayCheckoutOptions = {
  key: string;
  amount: number;
  currency: string;
  name: string;
  description: string;
  order_id: string;
  handler: (
    response: RazorpayCheckoutSuccess,
  ) => void;
  modal: {
    ondismiss: () => void;
    confirm_close: boolean;
    escape: boolean;
  };
  notes: Record<string, string>;
  theme: {
    color: string;
  };
};


type RazorpayCheckoutInstance = {
  open: () => void;
  on: (
    eventName: "payment.failed",
    handler: (
      response: RazorpayCheckoutFailure,
    ) => void,
  ) => void;
};


type RazorpayCheckoutConstructor = new (
  options: RazorpayCheckoutOptions,
) => RazorpayCheckoutInstance;


declare global {
  interface Window {
    Razorpay?: RazorpayCheckoutConstructor;
  }
}


export type RazorpayCheckoutResult =
  | {
      status: "payment_submitted";
      providerOrderId: string;
      providerPaymentId: string;
    }
  | {
      status: "payment_failed";
      providerOrderId: string;
      providerPaymentId: string | null;
      message: string;
    }
  | {
      status: "dismissed";
      providerOrderId: string;
    };


let checkoutScriptPromise: Promise<void> | null = null;


function existingCheckoutScript(): HTMLScriptElement | null {
  return document.querySelector<HTMLScriptElement>(
    `script[src="${RAZORPAY_CHECKOUT_SCRIPT_URL}"]`,
  );
}


export function loadRazorpayCheckout(): Promise<void> {
  if (window.Razorpay) {
    return Promise.resolve();
  }

  if (checkoutScriptPromise) {
    return checkoutScriptPromise;
  }

  checkoutScriptPromise = new Promise<void>(
    (resolve, reject) => {
      const existingScript = existingCheckoutScript();

      const handleLoad = () => {
        if (!window.Razorpay) {
          checkoutScriptPromise = null;
          reject(
            new Error(
              "Razorpay Checkout loaded without exposing its client",
            ),
          );
          return;
        }

        resolve();
      };

      const handleError = () => {
        checkoutScriptPromise = null;
        reject(
          new Error(
            "Unable to load Razorpay Checkout",
          ),
        );
      };

      if (existingScript) {
        existingScript.addEventListener(
          "load",
          handleLoad,
          { once: true },
        );
        existingScript.addEventListener(
          "error",
          handleError,
          { once: true },
        );
        return;
      }

      const script = document.createElement("script");
      script.src = RAZORPAY_CHECKOUT_SCRIPT_URL;
      script.async = true;
      script.addEventListener(
        "load",
        handleLoad,
        { once: true },
      );
      script.addEventListener(
        "error",
        handleError,
        { once: true },
      );

      document.head.appendChild(script);
    },
  );

  return checkoutScriptPromise;
}


function checkoutFailureMessage(
  response: RazorpayCheckoutFailure,
): string {
  const description = response.error?.description?.trim();

  if (description) {
    return description;
  }

  return "Razorpay reported that the Test Mode payment failed";
}


export async function openRazorpayTestCheckout(
  order: RazorpayTestCheckoutOrder,
): Promise<RazorpayCheckoutResult> {
  await loadRazorpayCheckout();

  const Razorpay = window.Razorpay;

  if (!Razorpay) {
    throw new Error(
      "Razorpay Checkout is unavailable",
    );
  }

  return new Promise<RazorpayCheckoutResult>(
    (resolve) => {
      let settled = false;

      const settle = (
        result: RazorpayCheckoutResult,
      ) => {
        if (settled) return;

        settled = true;
        resolve(result);
      };

      const checkout = new Razorpay({
        key: order.razorpay_key_id,
        amount: order.amount_paise,
        currency: order.currency,
        name: "RecoverAI",
        description: (
          "Provider-generated Test Mode payment"
        ),
        order_id: order.provider_order_id,
        handler: (response) => {
          // The signature is deliberately not logged or persisted by
          // the browser. Signed webhooks remain the source of truth.
          settle({
            status: "payment_submitted",
            providerOrderId: response.razorpay_order_id,
            providerPaymentId: response.razorpay_payment_id,
          });
        },
        modal: {
          ondismiss: () => {
            settle({
              status: "dismissed",
              providerOrderId: order.provider_order_id,
            });
          },
          confirm_close: true,
          escape: true,
        },
        notes: {
          recoverai_checkout_session_id:
            order.checkout_session_id,
          recoverai_data_source: order.data_source,
          recoverai_real_money: "false",
        },
        theme: {
          color: "#2f80ed",
        },
      });

      checkout.on(
        "payment.failed",
        (response) => {
          settle({
            status: "payment_failed",
            providerOrderId:
              response.error?.metadata?.order_id ??
              order.provider_order_id,
            providerPaymentId:
              response.error?.metadata?.payment_id ?? null,
            message: checkoutFailureMessage(response),
          });
        },
      );

      checkout.open();
    },
  );
}
