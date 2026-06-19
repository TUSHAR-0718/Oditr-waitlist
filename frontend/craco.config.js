// craco.config.js
const path = require("path");
require("dotenv").config();



// Environment variable overrides
const config = {
  enableHealthCheck: process.env.ENABLE_HEALTH_CHECK === "true",
};

// Conditionally load health check modules only if enabled
let WebpackHealthPlugin;
let setupHealthEndpoints;
let healthPluginInstance;

if (config.enableHealthCheck) {
  WebpackHealthPlugin = require("./plugins/health-check/webpack-health-plugin");
  setupHealthEndpoints = require("./plugins/health-check/health-endpoints");
  healthPluginInstance = new WebpackHealthPlugin();
}

let webpackConfig = {
  eslint: {
    configure: {
      extends: ["plugin:react-hooks/recommended"],
      rules: {
        "react-hooks/rules-of-hooks": "error",
        "react-hooks/exhaustive-deps": "warn",
      },
    },
  },
  webpack: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
    configure: (webpackConfig) => {

      // Add ignored patterns to reduce watched directories
        webpackConfig.watchOptions = {
          ...webpackConfig.watchOptions,
          ignored: [
            '**/node_modules/**',
            '**/.git/**',
            '**/build/**',
            '**/dist/**',
            '**/coverage/**',
            '**/public/**',
        ],
      };

      // Disable source maps for workers in development to avoid blob:// errors
      if (process.env.NODE_ENV === 'development') {
        webpackConfig.devtool = 'eval-source-map';
        // Filter out problematic rules
        webpackConfig.module.rules = webpackConfig.module.rules.map(rule => {
          if (rule.test && rule.test.toString().includes('worker')) {
            return {
              ...rule,
              options: { ...rule.options, sourceMap: false },
            };
          }
          return rule;
        });
      }

      // Add health check plugin to webpack if enabled
      if (config.enableHealthCheck && healthPluginInstance) {
        webpackConfig.plugins.push(healthPluginInstance);
      }
      return webpackConfig;
    },
  },
};

webpackConfig.devServer = (devServerConfig) => {
  // Fix WebSocket connection for dev server
  devServerConfig.client = {
    ...devServerConfig.client,
    webSocketURL: {
      hostname: 'localhost',
      pathname: '/ws',
      port: process.env.PORT || 3000,
      protocol: 'ws',
    },
  };

  // Add CORS headers to allow backend requests
  devServerConfig.headers = {
    ...devServerConfig.headers,
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
  };

  // Proxy API calls to backend
  devServerConfig.proxy = [
    {
      context: ['/api'],
      target: process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000',
      changeOrigin: true,
      pathRewrite: { '^/api': '/api' },
      ws: true,
    },
  ];

  // Add health check endpoints if enabled
  if (config.enableHealthCheck && setupHealthEndpoints && healthPluginInstance) {
    const originalSetupMiddlewares = devServerConfig.setupMiddlewares;

    devServerConfig.setupMiddlewares = (middlewares, devServer) => {
      // Call original setup if exists
      if (originalSetupMiddlewares) {
        middlewares = originalSetupMiddlewares(middlewares, devServer);
      }

      // Setup health endpoints
      setupHealthEndpoints(devServer, healthPluginInstance);

      return middlewares;
    };
  }

  return devServerConfig;
};



module.exports = webpackConfig;
