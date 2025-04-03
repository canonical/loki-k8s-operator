import React from "react";
import { Link } from "react-router-dom";
import { useBasename } from "../../contexts/BasenameContext";

interface BreadcrumbProps {
  parts: string[];
  isLastPartClickable?: boolean;
}

const getProviderStyles = (
  provider: string
): { bg: string; text: string; darkBg: string; darkText: string } => {
  switch (provider) {
    case "S3":
      return {
        bg: "bg-orange-100",
        text: "text-orange-800",
        darkBg: "dark:bg-orange-900",
        darkText: "dark:text-orange-300",
      };
    case "GCS":
      return {
        bg: "bg-blue-100",
        text: "text-blue-800",
        darkBg: "dark:bg-blue-900",
        darkText: "dark:text-blue-300",
      };
    case "AZURE":
      return {
        bg: "bg-sky-100",
        text: "text-sky-800",
        darkBg: "dark:bg-sky-900",
        darkText: "dark:text-sky-300",
      };
    case "SWIFT":
      return {
        bg: "bg-red-100",
        text: "text-red-800",
        darkBg: "dark:bg-red-900",
        darkText: "dark:text-red-300",
      };
    case "COS":
      return {
        bg: "bg-purple-100",
        text: "text-purple-800",
        darkBg: "dark:bg-purple-900",
        darkText: "dark:text-purple-300",
      };
    case "ALIYUNOSS":
      return {
        bg: "bg-rose-100",
        text: "text-rose-800",
        darkBg: "dark:bg-rose-900",
        darkText: "dark:text-rose-300",
      };
    case "OCI":
      return {
        bg: "bg-red-100",
        text: "text-red-800",
        darkBg: "dark:bg-red-900",
        darkText: "dark:text-red-300",
      };
    case "OBS":
      return {
        bg: "bg-cyan-100",
        text: "text-cyan-800",
        darkBg: "dark:bg-cyan-900",
        darkText: "dark:text-cyan-300",
      };
    case "FILESYSTEM":
      return {
        bg: "bg-green-100",
        text: "text-green-800",
        darkBg: "dark:bg-green-900",
        darkText: "dark:text-green-300",
      };
    case "MEMORY":
      return {
        bg: "bg-yellow-100",
        text: "text-yellow-800",
        darkBg: "dark:bg-yellow-900",
        darkText: "dark:text-yellow-300",
      };
    default:
      return {
        bg: "bg-gray-100",
        text: "text-gray-800",
        darkBg: "dark:bg-gray-700",
        darkText: "dark:text-gray-300",
      };
  }
};

export const Breadcrumb: React.FC<BreadcrumbProps> = ({
  parts,
  isLastPartClickable = false,
}) => {
  const [provider, setProvider] = React.useState<string>("");
  const basename = useBasename();
  React.useEffect(() => {
    fetch(`${basename}api/provider`)
      .then((res) => res.json())
      .then((data) => setProvider(data.provider))
      .catch(console.error);
  }, [basename]);

  const providerStyles = getProviderStyles(provider);

  return (
    <nav className="flex mb-4" aria-label="Breadcrumb">
      <ol className="inline-flex items-center space-x-1 md:space-x-3">
        <li className="inline-flex items-center">
          {provider && (
            <Link
              to="/"
              className={`inline-flex items-center h-7 gap-2 px-3 py-1 text-xs font-medium ${providerStyles.bg} ${providerStyles.text} ${providerStyles.darkBg} ${providerStyles.darkText} rounded-full hover:ring-2 hover:ring-gray-300 dark:hover:ring-gray-600 transition-all duration-200`}
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 576 512"
                className="w-4 h-4"
                fill="currentColor"
              >
                <path d="M575.8 255.5c0 18-15 32.1-32 32.1h-32l.7 160.2c0 2.7-.2 5.4-.5 8.1V472c0 22.1-17.9 40-40 40H456c-1.1 0-2.2 0-3.3-.1c-1.4 .1-2.8 .1-4.2 .1H416 392c-22.1 0-40-17.9-40-40V448 384c0-17.7-14.3-32-32-32H256c-17.7 0-32 14.3-32 32v64 24c0 22.1-17.9 40-40 40H160 128.1c-1.5 0-3-.1-4.5-.2c-1.2 .1-2.4 .2-3.6 .2H104c-22.1 0-40-17.9-40-40V360c0-.9 0-1.9 .1-2.8V287.6H32c-18 0-32-14-32-32.1c0-9 3-17 10-24L266.4 8c7-7 15-8 22-8s15 2 21 7L564.8 231.5c8 7 12 15 11 24z" />
              </svg>
              {provider}
            </Link>
          )}
        </li>
        {parts.map((part, index, array) => (
          <li key={index}>
            <div className="flex items-center">
              <svg
                className="w-3 h-3 text-gray-400 mx-1"
                aria-hidden="true"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 6 10"
              >
                <path
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="m1 9 4-4-4-4"
                />
              </svg>
              {!isLastPartClickable && index === array.length - 1 ? (
                <span className="ml-1 text-sm font-medium text-gray-500 md:ml-2">
                  {part}
                </span>
              ) : (
                <Link
                  to={`/?path=${encodeURIComponent(
                    array.slice(0, index + 1).join("/")
                  )}`}
                  className="ml-1 text-sm font-medium text-gray-500 hover:text-blue-600 dark:text-gray-400 dark:hover:text-blue-400 md:ml-2"
                >
                  {part}
                </Link>
              )}
            </div>
          </li>
        ))}
      </ol>
    </nav>
  );
};
