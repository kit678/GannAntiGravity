# Dhan API V2 Documentation

Scraped from https://dhanhq.co/docs/v2/ on win32



# Source: https://dhanhq.co/docs/v2/

# Introduction

## Getting Started

![alt](img/intro.svg)

DhanHQ API is a state-of-the-art platform for you to build trading and investment services & strategies.

It is a set of REST-like APIs that provide integration with our trading platform. Execute & modify orders in real time,
manage portfolio, access live market data and more, with lightning fast API collection.

We offer resource-based URLs that accept JSON or form-encoded requests. The response is returned as
JSON-encoded responses by using Standard HTTP response codes, verbs, and authentication.





![sandbox](img/btn2sandbox.png)

Developer Kit

[Explore Now
![sandbox](img/dhanhq-arrow.png)](https://api.dhan.co/v2/#)

![sandbox](img/btn2sandbox.png)

Developer Kit

[Explore Now](https://api.dhan.co/v2/#)
![sandbox](img/dhanhq-arrow.png)

![python](img/btn2pydhanhq.png)

DhanHQ Python Client

[Explore Now
![python](img/dhanhq-arrow.png)](https://pypi.org/project/dhanhq/)

![python](img/btn2pydhanhq.png)

DhanHQ Python Client

[Explore Now](https://pypi.org/project/dhanhq/)
![python](img/dhanhq-arrow.png)

## Structure

RESTPython

All GET and DELETE request parameters go as query parameters, and POST and PUT parameters as form-encoded.
User has to input an access token in the header for every request.

```python
curl --request POST \
--url https://api.dhan.co/v2/ \
--header 'Content-Type: application/json' \
--header 'access-token: JWT' \
--data '{Request JSON}'
```

Install Python Package directly using following command in command line.

```python
pip install dhanhq
```

This installs entire DhanHQ Python Client along with the required packages. Now, you can start using DhanHQ Client with your Python script.

You can now import 'dhanhq' module and connect to your Dhan account.

```python
from dhanhq import dhanhq

dhan = dhanhq("client_id","access_token")
```

## Errors

Error responses come with the error code and message generated internally by the system. The sample structure of
error response is shown below.

```python
{
    "errorType": "",
    "errorCode": "",
    "errorMessage": ""
}
```

You can find detailed error code and message under [Annexure](/docs/v2/annexure/#trading-api-error).

## Rate Limit

| Rate Limit | Order APIs | Data APIs | Quote APIs | Non Trading APIs |
| --- | --- | --- | --- | --- |
| per second | 25 | 5 | 1 | 20 |
| per minute | 250 | - | Unlimited | Unlimited |
| per hour | 1000 | - | Unlimited | Unlimited |
| per day | 7000 | 100000 | Unlimited | Unlimited |

Order Modifications are capped at 25 modifications/order

---


# Source: https://dhanhq.co/docs/v2/releases/

# Release Notes

## Version 2.4

*Date: Monday Sep 22 2025*

In line with the changes in SEBI guidelines on Retail Participation in Algorithmic Trading, we are bringing changes to the authentication module - primarily in 3 areas - reduced Access Token duration, API Key based authentication and IP setup.

### New Features

* **API Key based login**  
  We have introduced a new authentication module for accessing APIs - API key and secret for individuals. You can now use this method to generate API key for one year validity and generate new access token daily by verifying your Dhan credentials. You can read more about the same [here](/docs/v2/authentication/#api-key-secret).

### Breaking Changes

* **Access Token can only be generated for 24 hours**  
  Access token based authentication will only be allowed for 24 hours after generating token. This is in line with the exchange and SEBI guidelines on management of API access.
* **Static IP Requirement**  
  Static IP is required for all Order APIs for placing, modifying and cancelling any type of orders - including normal orders, super orders and forever orders. You can setup IP directly via API as per the [.Setup Static IP APIs](/docs/v2/authentication/#setup-static-ip).

## Version 2.3

*Date: Monday Sep 08 2025*

We are adding one of the most requested data on APIs - 200 Market Depth on Websockets and historical expired options contract data. Along with this, we are changing rate limit for Order APIs to 10 order per second, in accordance with regulations.

### New Features

* **Full Market Depth**  
  You can get depth upto 200 levels directly on websocket - an extension of 20 Market Depth with more data so you can design trading system on top of more data and find our opportunity zones seamlessly. You can read more about how this will work [here](/docs/v2/full-market-depth/#200-level).
* **Historical Options Data**  
  This endpoint is built for you to fetch options data of expired contracts, on a rolling basis. You do not need to look for the security ID for expired contracts, rather you can enter strikes as ATM +/- to fetch data. You can also get rolling IV, OI and volumes directly from [here](/docs/v2/expired-options-data).

## Version 2.2

*Date: Friday Mar 07 2025*

We are adding a new order type on Dhan and which is available on v2 of DhanHQ API. This order type is called Super Order. This along with a major update to Historical Data APIs is added. You can now fetch upto last 5 years of Intraday Historical Data (minutewise) and also OI data for futures and options instruments.

### New Features

* **Super Orders**  
  Super Orders are a new order type which allows you to combine multiple orders for entry and exit into single order. You can enter a position and place target and stop loss orders for the same along with the option to trail your stop loss. This combines the benefits of a bracket order and a trailing stop, and is available across all exchanges and segments - [Super Order](/docs/v2/super-order).
* **User Profile**  
  User Profile API is built to give a status check about different information related to user's account. This includes token validity, active segments, Data API subscription status and validity, and different user configurations like DDPI status and MTF enablement - [here](/docs/v2/#user-profile).

### Improvements

* **Intraday Historical Data**  
  Intraday Historical Data is now available for last 5 years of data. This is available for all NSE, BSE and MCX instruments. Along with increase in time range, we have also added OI data for futures and options instruments. There is `oi` parameter added to the API. Also, the `from_date` and `to_date` has option to pass IST time as well to fetch particular number of bars only. You can head over to documentation for updates in fields - [here](/docs/v2/historical-data/#intraday-historical-data).
* **Daily Historical Data**  
  Daily Historical Data has added OI data for futures and options instruments. There is `oi` parameter added to the API which is *optional* and can be used to fetch OI data - [here](/docs/v2/historical-data/#daily-historical-data).
* **`CorrelationId` on Live Order Update**  
  Live Order Update now has two additional keys called 'CorrelationId' and 'Remarks' - [here](/docs/v2/order-update/#order-update).

### Breaking Changes

* **Changes in Rate Limit**  
  Rate limits have been increased for Data APIs which includes Historical Data. There are no rate limits on minute and hourly time frames. You can request upto 1,00,000 requests in a day and seconds timeframe are limited to 5 requests per second - [Rate Limit](/docs/v2/#rate-limits).

## Version 2.1

*Date: Monday Jan 06 2025*

This add-on to DhanHQ v2 comes with 20 level market depth (Level 3 data) for APIs. Along with that, this also covers Option Chain API, which was released in between and smaller enhancements.

### New Features

* **20 Market Depth**  
  You can get real-time streaming of 20 level market depth, for all NSE instruments with [20 Market Depth](/docs/v2/full-market-depth). It is delivered via websockets and can be used to detect demand-supply zones and build your systems on top of it.
* **Option Chain**  
  Dhan's Advanced Option Chain is made available on a single API request, for any underlying. With this, you get OI, greeks, volume, top bid/ask and price data of all strikes of any Option Instrument, across exchanges and segments - for NSE, BSE and MCX traded options - [Option Chain API](/docs/v2/option-chain).

### Improvements

* **'expiryCode' in Daily Historical Data**  
  Daily Historical Data now has expiryCode as an *"Optional"* field - [Daily Historical Data API](/docs/v2/historical-data/#daily-historical-data).

## Version 2

*Date: Monday Sep 15 2024*

DhanHQ v2 extends execution capability with live order updates and forever orders on superfast APIs. Along with this, we also released Market Quote APIs, built on top of Live Market Feed which can be integrated with ease. We have also introduced improvements, bug fixes and increased stability with new version.

### New Features

* **Market Quote**  
  Fetch LTP, Quote (with OI) and Market Depth data directly on API, for upto 1000 instruments at once with [Market Quote API](/docs/v2/market-quote).
* **Forever Orders**  
  Place, modify and manage your Forever Orders, including single and OCO orders to manage risk and trade efficiently with [Forever Order API](/docs/v2/forever).
* **Live Order Update**  
  Order Updates are sent in real time via websockets, which will update order status of all your orders placed via any platform - [Live Order Update](/docs/v2/order-update).
* **Margin Calculator**  
  Margin Calculation simplifies order placement by providing details about required margin and available balances before placing order - [Margin Calculator API](/docs/v2/funds/#margin-calculator).

### Improvements

* **Intraday Historical Data**  
  Intraday Historical Data now provides OHLC with Volume data for last 5 trading days across timeframes such as 1 min, 5 min, 15 min, 25 min and 60 min - [Intraday Historical Data API](/docs/v2/historical-data/#intraday-historical-data).
* **GET Order APIs**  
  `filledQty`, `remainingQuantity` and `averageTradedPrice` is available as part of all GET Order APIs, which makes it simpler to fetch post execution details of an order. We have also added `PART_TRADED` as a flag on `orderStatus` which will be clear distinction for partially traded orders.
* **Live Market Feed**  
  You can now authorise [Live Market Feed](/docs/v2/live-market-feed/) via Query Parameters and subscribe/unsubscribe to instruments via JSON messages on websockets with this version. Also, `FULL` packet is now available which will gives LTP, Quote, OI and Market Depth data in a single packet.

### Breaking Changes

* **Order Placement**  
  Deprecated non-mandatory request keys including `tradingSymbol`, `drvExpiryDate`, `drvOptionType` and `drvStrikePrice` from Order Placement API endpoints. Along with this, pre-open AMO orders can also be placed now with `PRE_OPEN` tag.
* **Order Modification**  
  `quantity` field needs to be placed order quantity instead of pending order quantity. Earlier, for Order Modification API, in case of partial execution, user needed to pass pending order quantity, which led to errors due to simultaneous execution on exchange or need to call GET Trade APIs as well.
  `quantity` and `price` fields are conditionally required for modification.

  `quantity` field in Order Modification
* **Daily Historical Data**  
  `symbol` is replaced with `securityId` as key in Daily Historical Data, making it simple for users to fetch data everywhere with Security ID itself - [Daily Historical Data API](/docs/v2/historical-data/#daily-historical-data).
* **Error Messages**  
  Now error messages are categorised with DH-900 series which helps you self debug on level of error - [Error Codes](/docs/v2/#errors).
* **Security ID List Mapping**  
  Security ID List is now comprehensive with tag changes as well. Check new mappings and description - [Security ID List](/docs/v2/instruments).
* **Epoch time introduced instead of Julian time in Historical Data APIs** -
  Timestamp in [Daily Historical Data API](/docs/v2/historical-data/#daily-historical-data) and [Intraday Historical Data API](/docs/v2/historical-data/#intraday-historical-data) is now Epoch or UNIX time and with key `timestamp`.
* **`Market Depth` deprecated as mode in Live Market Feed**  
  `Market Depth` mode is now replaced with `FULL` packet which has combined data of Quote, OI and market depth in single packet, enabling ease in subscribing and fetching data.
* **Change in endpoint for Trade History and Kill Switch**  
  New endpoint for Trade History is `/trades`, making it common with other Trade book APIs. For Kill Switch, the new endpoint as per nomenclature is `killswitch`.

### Bug Fixes

* **`realizedProfit` and `unrealizedProfit` in Positions API**  
  You can now get realtime values of `realizedProfit` and `unrealizedProfit` on [Positions API](/docs/v2/portfolio/#positions).
* **Target leg modification in Order Modification API**  
  `TARGET_LEG` was not getting modified with [Order Modification API](/docs/v2/orders/#order-modification) which is fixed now.

---


# Source: https://dhanhq.co/docs/v2/orders/

# Orders

The order management API lets you place a new order, cancel or modify the pending order, retrieve the order status, trade status, order book & tradebook.

|  |  |  |
| --- | --- | --- |
| POST | /orders | Place a new order |
| PUT | /orders/{order-id} | Modify a pending order |
| DELETE | /orders/{order-id} | Cancel a pending order |
| POST | /orders/slicing | Slice order into multiple legs over freeze limit |
| GET | /orders | Retrieve the list of all orders for the day |
| GET | /orders/{order-id} | Retrieve the status of an order |
| GET | /orders/external/{correlation-id} | Retrieve the status of an order by correlation id |
| GET | /trades | Retrieve the list of all trades for the day |
| GET | /trades/{order-id} | Retrieve the details of trade by an order id |

Order Placement, Modification and Cancellation APIs requires Static IP whitelisting - [here](/docs/v2/authentication/#setup-static-ip)

## Order Placement

The order request API lets you place new orders.

```python
    curl --request POST \
    --url https://api.dhan.co/v2/orders \
    --header 'Content-Type: application/json' \
    --header 'access-token: JWT' \
    --data '{Request JSON}'
```

**Request Structure**

```python
    {
        "dhanClientId":"1000000003",
        "correlationId":"123abc678",
        "transactionType":"BUY",
        "exchangeSegment":"NSE_EQ",
        "productType":"INTRADAY",
        "orderType":"MARKET",
        "validity":"DAY",
        "securityId":"11536",
        "quantity":"5",
        "disclosedQuantity":"",
        "price":"",
        "triggerPrice":"",
        "afterMarketOrder":false,
        "amoTime":"",
        "boProfitValue":"",
        "boStopLossValue": ""
    }
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| dhanClientId   *required* | string | User specific identification generated by Dhan |
| correlationId | string | The user/partner generated id for tracking back. |
| transactionType   *required* | enum string | The trading side of transaction   `BUY`  `SELL` |
| exchangeSegment   *required* | enum string | Exchange Segment of instrument to be subscribed as found in [Annexure](/docs/v2/annexure/#exchange-segment) |
| productType   *required* | enum string | Product type `CNC`  `INTRADAY` `MARGIN` `MTF`  `CO` `BO` |
| orderType  *required* | enum string | Order Type  `LIMIT`  `MARKET`  `STOP_LOSS`  `STOP_LOSS_MARKET` |
| validity  *required* | enum string | Validity of Order  `DAY` `IOC` |
| securityId  *required* | string | Exchange standard ID for each scrip. Refer [here](/docs/v2/instruments/) |
| quantity *required* | int | Number of shares for the order |
| disclosedQuantity | int | Number of shares visible (Keep more than 30% of quantity) |
| price  *required* | float | Price at which order is placed |
| triggerPrice  *conditionally required* | float | Price at which the order is triggered, in case of SL-M & SL-L |
| afterMarketOrder  *conditionally required* | boolean | Flag for orders placed after market hours |
| amoTime  *conditionally required* | enum sting | Timing to pump the after market order   `PRE_OPEN` `OPEN` `OPEN_30` `OPEN_60` |
| boProfitValue  *conditionally required* | float | Bracket Order Target Price change |
| boStopLossValue   *conditionally required* | float | Bracket Order Stop Loss Price change |

**Response Structure**

```python
{
    "orderId": "112111182198",
    "orderStatus": "PENDING",
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| orderId | string | Order specific identification generated by Dhan |
| orderStatus | enum string | Last updated status of the order   `TRANSIT` `PENDING` `REJECTED` `CANCELLED` `TRADED` `EXPIRED` |

## Order Modification

Using this API one can modify pending order in orderbook. The variables that can be modified are price,
quantity, order type & validity. The user has to mention the desired value in fields.

```python
    curl --request PUT \
    --url https://api.dhan.co/v2/orders/{order-id} \
    --header 'Content-Type: application/json' \
    --header 'access-token: JWT' \
    --data '{Request JSON}'
```

**Request Structure**

```python
    {
        "dhanClientId":"1000000009",
        "orderId":"112111182045",
        "orderType":"LIMIT",
        "legName":"",
        "quantity":"40",
        "price":"3345.8",
        "disclosedQuantity":"10",
        "triggerPrice":"",
        "validity":"DAY"
    }
```

**Parameters**

| Field | Type | description |
| --- | --- | --- |
| dhanClientId    *required* | string | User specific identification generated by Dhan |
| orderId    *required* | string | Order specific identification generated by Dhan |
| orderType    *required* | enum string | Order Type   `LIMIT` `MARKET` `STOP_LOSS` `STOP_LOSS_MARKET` |
| legName   *conditionally required* | enum string | In case of BO & CO, which leg is modified   `ENTRY_LEG` `TARGET_LEG` `STOP_LOSS_LEG` |
| quantity   *conditionally required* | int | Quantity to be modified |
| price   *conditionally required* | float | Price to be modified |
| disclosedQuantity | int | Number of shares visible (if opting keep >30% of quantity) |
| triggerPrice   *conditionally required* | float | Price at which the order is triggered, in case of SL-M & SL-L |
| validity   *required* | enum string | Validity of Order   `DAY` `IOC` |

**Response Structure**

```python
{
    "orderId": "112111182045",
    "orderStatus": "TRANSIT"
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| orderId | string | Order specific identification generated by Dhan |
| orderStatus | enum string | Last updated status of the order   `TRANSIT` `PENDING` `REJECTED` `CANCELLED` `TRADED` `EXPIRED` |

## Order Cancellation

Users can cancel a pending order in the orderbook using the order id of an order. There is no body for
request and response for this call. On successful completion of request ‘202 Accepted’ response status code
will appear.

```python
    curl --request DELETE \
    --url https://api.dhan.co/v2/orders/{order-id} \
    --header 'Content-Type: application/json' \
    --header 'access-token: JWT'
```

**Request Structure**

*No Body*

**Response Structure**

```python
{
"orderId": "112111182045",
"orderStatus": "CANCELLED"
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| orderId | string | Order specific identification generated by Dhan |
| orderStatus | enum string | Last updated status of the order   `TRANSIT` `PENDING` `REJECTED` `CANCELLED` `TRADED` `EXPIRED` |

## Order Slicing

This API helps you slice your order request into multiple orders to allow you to place over freeze limit quantity for F&O instruments.

cURLPython

```python
curl --request POST \
--url https://api.dhan.co/v2/orders/slicing \
--header 'Content-Type: application/json' \
--header 'access-token: JWT'
--data '{Request JSON}'
```

```python
dhan.place_slice_order(data)
```

**Request Structure**

```python
    {
        "dhanClientId":"1000000003",
        "correlationId":"123abc678",
        "transactionType":"BUY",
        "exchangeSegment":"NSE_EQ",
        "productType":"INTRADAY",
        "orderType":"MARKET",
        "validity":"DAY",
        "securityId":"11536",
        "quantity":"5",
        "disclosedQuantity":"",
        "price":"",
        "triggerPrice":"",
        "afterMarketOrder":false,
        "amoTime":"",
        "boProfitValue":"",
        "boStopLossValue": ""
    }
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| dhanClientId   *required* | string | User specific identification generated by Dhan |
| correlationId | string | The user/partner generated id for tracking back. |
| transactionType   *required* | enum string | The trading side of transaction    `BUY`    `SELL` |
| exchangeSegment   *required* | enum string | Exchange & Segment  Exchange Segment of instrument to be subscribed as found in [Annexure](/docs/v2/annexure/#exchange-segment) | |
| productType   *required* | enum string | Product type `CNC`  `INTRADAY` `MARGIN` `MTF`  `CO` `BO` |
| orderType  *required* | enum string | Order Type  `LIMIT`  `MARKET`  `STOP_LOSS`  `STOP_LOSS_MARKET` |
| validity  *required* | enum string | Validity of Order  `DAY` `IOC` |
| securityId  *required* | string | Exchange standard ID for each scrip. Refer [here](/docs/v2/instruments/) |
| quantity  *required* | int | Number of shares for the order |
| disclosedQuantity | int | Number of shares visible (Keep more than 30% of quantity) |
| price  *required* | float | Price at which order is placed |
| triggerPrice  *conditionally required* | float | Price at which the order is triggered, in case of SL-M & SL-L |
| afterMarketOrder  *conditionally required* | boolean | Flag for orders placed after market hours |
| amoTime  *conditionally required* | enum sting | Timing to pump the after market order   `PRE_OPEN` `OPEN` `OPEN_30` `OPEN_60` |
| boProfitValue  *conditionally required* | float | Bracket Order Target Price change |
| boStopLossValue   *conditionally required* | float | Bracket Order Stop Loss Price change |

**Response Structure**

```python
[
    {
        "orderId": "552209237100",
        "orderStatus": "TRANSIT"
    },
    {
        "orderId": "552209237100",
        "orderStatus": "TRANSIT"
    }
]
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| orderId | string | Order specific identification generated by Dhan |
| orderStatus | string | Order Type  `TRANSIT` `PENDING` `REJECTED` `CANCELLED` `TRADED` `EXPIRED` `CONFIRM` |

## Order Book

This API lets you retrieve an array of all orders requested in a day with their last updated status.

```python
    curl --request GET \
    --url https://api.dhan.co/v2/orders \
    --header 'Content-Type: application/json' \
    --header 'access-token: JWT'
```

**Request Structure**

*No Body*

**Response Structure**

```python
[
    {
        "dhanClientId": "1000000003",
        "orderId": "112111182198",
        "correlationId":"123abc678",
        "orderStatus": "PENDING",
        "transactionType": "BUY",
        "exchangeSegment": "NSE_EQ",
        "productType": "INTRADAY",
        "orderType": "MARKET",
        "validity": "DAY",
        "tradingSymbol": "",
        "securityId": "11536",
        "quantity": 5,
        "disclosedQuantity": 0,
        "price": 0.0,
        "triggerPrice": 0.0,
        "afterMarketOrder": false,
        "boProfitValue": 0.0,
        "boStopLossValue": 0.0,
        "legName": ,
        "createTime": "2021-11-24 13:33:03",
        "updateTime": "2021-11-24 13:33:03",
        "exchangeTime": "2021-11-24 13:33:03",
        "drvExpiryDate": null,
        "drvOptionType": null,
        "drvStrikePrice": 0.0,
        "omsErrorCode": null,
        "omsErrorDescription": null,
        "algoId": "string"
        "remainingQuantity": 5,
        "averageTradedPrice": 0,
        "filledQty": 0
    }
]
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| dhanClientId | string | User specific identification generated by Dhan |
| orderId | string | Order specific identification generated by Dhan |
| correlationId | string | The user/partner generated id for tracking back |
| orderStatus | enum string | Last updated status of the order   `TRANSIT` `PENDING` `REJECTED` `CANCELLED` `PART_TRADED` `TRADED` `EXPIRED` |
| transactionType | enum string | The trading side of transaction   `BUY` `SELL` |
| exchangeSegment | enum string | Exchange Segment of instrument to be subscribed as found in [Annexure](/docs/v2/annexure/#exchange-segment) |
| productType | enum string | Product type of trade `CNC`  `INTRADAY` `MARGIN` `MTF`  `CO` `BO` |
| orderType | enum string | Order Type  `LIMIT`  `MARKET`  `STOP_LOSS`  `STOP_LOSS_MARKET` |
| validity | enum string | Validity of Order  `DAY` `IOC` |
| tradingSymbol | string | Refer Trading Symbol in Tables |
| securityId | string | Exchange standard ID for each scrip. Refer [here](/docs/v2/instruments/) |
| quantity | int | Number of shares for the order |
| disclosedQuantity | int | Number of shares visible |
| price | float | Price at which order is placed |
| triggerPrice | float | Price at which order is triggered, for SL-M, SL-L, CO & BO |
| afterMarketOrder | boolean | The order placed is AMO ? |
| boProfitValue | float | Bracket Order Target Price change |
| boStopLossValue | float | Bracket Order Stop Loss Price change |
| legName | enum string | Leg identification in case of BO   `ENTRY_LEG` `TARGET_LEG` `STOP_LOSS_LEG` |
| createTime | string | Time at which the order is created |
| updateTime | string | Time at which the last activity happened |
| exchangeTime | string | Time at which order reached at exchange |
| drvExpiryDate | string | For F&O, expiry date of contract |
| drvOptionType | enum string | Type of Option   `CALL` `PUT` |
| drvStrikePrice | float | For Options, Strike Price |
| omsErrorCode | string | Error code in case the order is rejected or failed |
| omsErrorDescription | string | Description of error in case the order is rejected or failed |
| algoId | string | Exchange Algo ID for Dhan |
| remainingQuantity | integer | Quantity pending at the exchange to be traded (quantity - filledQty) |
| averageTradedPrice | integer | Average price at which order is traded |
| filledQty | integer | Quantity of order traded on Exchange |

## Get Order by Order Id

Users can retrieve the details and status of an order from the orderbook placed during the day.

```python
    curl --request GET \
    --url https://api.dhan.co/v2/orders/{order-id} \
    --header 'Content-Type: application/json' \
    --header 'access-token: JWT'
```

**Request Structure**

*No Body*

**Response Structure**

```python
{
    "dhanClientId": "1000000003",
    "orderId": "112111182198",
    "correlationId":"123abc678",
    "orderStatus": "PENDING",
    "transactionType": "BUY",
    "exchangeSegment": "NSE_EQ",
    "productType": "INTRADAY",
    "orderType": "MARKET",
    "validity": "DAY",
    "tradingSymbol": "",
    "securityId": "11536",
    "quantity": 5,
    "disclosedQuantity": 0,
    "price": 0.0,
    "triggerPrice": 0.0,
    "afterMarketOrder": false,
    "boProfitValue": 0.0,
    "boStopLossValue": 0.0,
    "legName": ,
    "createTime": "2021-11-24 13:33:03",
    "updateTime": "2021-11-24 13:33:03",
    "exchangeTime": "2021-11-24 13:33:03",
    "drvExpiryDate": null,
    "drvOptionType": null,
    "drvStrikePrice": 0.0,
    "omsErrorCode": null,
    "omsErrorDescription": null,
    "algoId": "string"
    "remainingQuantity": 5,
    "averageTradedPrice": 0,
    "filledQty": 0
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| dhanClientId | string | User specific identification generated by Dhan |
| orderId | string | Order specific identification generated by Dhan |
| correlationId | string | The user/partner generated id for tracking back |
| orderStatus | enum string | Last updated status of the order   `TRANSIT` `PENDING` `REJECTED` `CANCELLED` `PART_TRADED` `TRADED` `EXPIRED` |
| transactionType | enum string | The trading side of transaction   `BUY` `SELL` |
| exchangeSegment | enum string | Exchange Segment of instrument to be subscribed as found in [Annexure](/docs/v2/annexure/#exchange-segment) |
| productType | enum string | Product type of trade `CNC`  `INTRADAY` `MARGIN` `MTF`  `CO` `BO` |
| orderType | enum string | Order Type  `LIMIT`  `MARKET`  `STOP_LOSS`  `STOP_LOSS_MARKET` |
| validity | enum string | Validity of Order  `DAY` `IOC` |
| tradingSymbol | string | Refer Trading Symbol in Tables |
| securityId | string | Exchange standard ID for each scrip. Refer [here](/docs/v2/instruments/) |
| quantity | int | Number of shares for the order |
| disclosedQuantity | int | Number of shares visible |
| price | float | Price at which order is placed |
| triggerPrice | float | Price at which order is triggered, for SL-M, SL-L, CO & BO |
| afterMarketOrder | boolean | The order placed is AMO ? |
| boProfitValue | float | Bracket Order Target Price change |
| boStopLossValue | float | Bracket Order Stop Loss Price change |
| legName | enum string | Leg identification in case of BO   `ENTRY_LEG` `TARGET_LEG` `STOP_LOSS_LEG` |
| createTime | string | Time at which the order is created |
| updateTime | string | Time at which the last activity happened |
| exchangeTime | string | Time at which order reached at exchange |
| drvExpiryDate | string | For F&O, expiry date of contract |
| drvOptionType | enum string | Type of Option   `CALL` `PUT` |
| drvStrikePrice | float | For Options, Strike Price |
| omsErrorCode | string | Error code in case the order is rejected or failed |
| omsErrorDescription | string | Description of error in case the order is rejected or failed |
| algoId | string | Exchange Algo ID for Dhan |
| remainingQuantity | integer | Quantity pending at the exchange to be traded (quantity - filledQty) |
| averageTradedPrice | integer | Average price at which order is traded |
| filledQty | integer | Quantity of order traded on Exchange |

## Get Order by Correlation Id

In case the user has missed order id due to unforeseen reason, this API retrieves the order status using a tag
called correlation id specified by users themselve.

```python
    curl --request GET \
    --url https://api.dhan.co/v2/orders/external/{correlation-id} \
    --header 'Content-Type: application/json' \
    --header 'access-token: JWT'
```

**Request Structure**

*No Body*

**Response Structure**

```python
{
    "dhanClientId": "1000000003",
    "orderId": "112111182198",
    "correlationId":"123abc678",
    "orderStatus": "PENDING",
    "transactionType": "BUY",
    "exchangeSegment": "NSE_EQ",
    "productType": "INTRADAY",
    "orderType": "MARKET",
    "validity": "DAY",
    "tradingSymbol": "",
    "securityId": "11536",
    "quantity": 5,
    "disclosedQuantity": 0,
    "price": 0.0,
    "triggerPrice": 0.0,
    "afterMarketOrder": false,
    "boProfitValue": 0.0,
    "boStopLossValue": 0.0,
    "legName": ,
    "createTime": "2021-11-24 13:33:03",
    "updateTime": "2021-11-24 13:33:03",
    "exchangeTime": "2021-11-24 13:33:03",
    "drvExpiryDate": null,
    "drvOptionType": null,
    "drvStrikePrice": 0.0,
    "omsErrorCode": null,
    "omsErrorDescription": null,
    "algoId": "string"
    "remainingQuantity": 5,
    "averageTradedPrice": 0,
    "filledQty": 0
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| dhanClientId | string | User specific identification generated by Dhan |
| orderId | string | Order specific identification generated by Dhan |
| correlationId | string | The user/partner generated id for tracking back |
| orderStatus | enum string | Last updated status of the order   `TRANSIT` `PENDING` `REJECTED` `CANCELLED` `PART_TRADED` `TRADED` `EXPIRED` |
| transactionType | enum string | The trading side of transaction   `BUY` `SELL` |
| exchangeSegment | enum string | Exchange Segment of instrument to be subscribed as found in [Annexure](/docs/v2/annexure/#exchange-segment) |
| productType | enum string | Product type of trade `CNC`  `INTRADAY` `MARGIN` `MTF`  `CO` `BO` |
| orderType | enum string | Order Type  `LIMIT`  `MARKET`  `STOP_LOSS`  `STOP_LOSS_MARKET` |
| validity | enum string | Validity of Order  `DAY` `IOC` |
| tradingSymbol | string | Refer Trading Symbol in Tables |
| securityId | string | Exchange standard ID for each scrip. Refer [here](/docs/v2/instruments/) |
| quantity | int | Number of shares for the order |
| disclosedQuantity | int | Number of shares visible |
| price | float | Price at which order is placed |
| triggerPrice | float | Price at which order is triggered, for SL-M, SL-L, CO & BO |
| afterMarketOrder | boolean | The order placed is AMO ? |
| boProfitValue | float | Bracket Order Target Price change |
| boStopLossValue | float | Bracket Order Stop Loss Price change |
| legName | enum string | Leg identification in case of BO   `ENTRY_LEG` `TARGET_LEG` `STOP_LOSS_LEG` |
| createTime | string | Time at which the order is created |
| updateTime | string | Time at which the last activity happened |
| exchangeTime | string | Time at which order reached at exchange |
| drvExpiryDate | string | For F&O, expiry date of contract |
| drvOptionType | enum string | Type of Option   `CALL` `PUT` |
| drvStrikePrice | float | For Options, Strike Price |
| omsErrorCode | string | Error code in case the order is rejected or failed |
| omsErrorDescription | string | Description of error in case the order is rejected or failed |
| algoId | string | Exchange Algo ID for Dhan |
| remainingQuantity | integer | Quantity pending at the exchange to be traded (quantity - filledQty) |
| averageTradedPrice | integer | Average price at which order is traded |
| filledQty | integer | Quantity of order traded on Exchange |

## Trade Book

This API lets you retrieve an array of all trades executed in a day.

```python
    curl --request GET \
    --url https://api.dhan.co/v2/trades \
    --header 'Content-Type: application/json' \
    --header 'access-token: JWT'
```

**Request Structure**

*No Body*

**Response Structure**

```python
[
    {
        "dhanClientId": "1000000009",
        "orderId": "112111182045",
        "exchangeOrderId": "15112111182045",
        "exchangeTradeId": "15112111182045",
        "transactionType": "BUY",
        "exchangeSegment": "NSE_EQ",
        "productType": "INTRADAY",
        "orderType": "LIMIT",
        "tradingSymbol": "TCS",
        "securityId": "11536",
        "tradedQuantity": 40,
        "tradedPrice": 3345.8,
        "createTime": "2021-03-10 11:20:06",
        "updateTime": "2021-11-25 17:35:12"
        "exchangeTime": "2021-11-25 17:35:12",
        "drvExpiryDate": null,
        "drvOptionType": null,
        "drvStrikePrice": 0.0
    }
]
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| dhanClientId | string | User specific identification generated by Dhan |
| orderId | string | Order specific identification generated by Dhan |
| exchangeOrderId | string | Order specific identification generated by exchange |
| exchangeTradeId | string | Trade specific identification generated by exchange |
| transactionType | enum string | The trading side of transaction  `BUY` `SELL` |
| exchangeSegment | enum string | Exchange Segment of instrument to be subscribed as found in [Annexure](/docs/v2/annexure/#exchange-segment) |
| productType | enum string | Product type of trade `CNC`  `INTRADAY` `MARGIN` `MTF`  `CO` `BO` |
| orderType | enum string | Order Type  `LIMIT`  `MARKET`  `STOP_LOSS`  `STOP_LOSS_MARKET` |
| tradingSymbol | string | Refer Trading Symbol in Tables |
| securityId | string | Exchange standard ID for each scrip.Refer [here](/docs/v2/instruments/) |
| tradedQuantity | int | Number of shares executed |
| tradedPrice | float | Price at which trade is executed |
| createTime | string | Time at which the order is created |
| updateTime | string | Time at which the last activity happened |
| exchangeTime | string | Time at which order reached at exchange |
| drvExpiryDate | string | For F&O, expiry date of contract |
| drvOptionType | enum string | Type of Option   `CALL` `PUT` |
| drvStrikePrice | float | For Options, Strike Price |

## Trades of an Order

Users can retrieve the trade details using an order id. Often during partial trades or Bracket/ Cover Orders,
traders get confused in reading trade from tradebook.The response of this API will include all the trades
generated for a particular order id.

cURLPython

```python
curl --request GET \
--url https://api.dhan.co/v2/trades/{order-id} \
--header 'Content-Type: application/json' \
--header 'access-token: JWT'
```

```python
dhan.get_trade_book(order_id)
```

**Request Structure**

*No Body*

**Response Structure**

```python
{
    "dhanClientId": "1000000009",
    "orderId": "112111182045",
    "exchangeOrderId": "15112111182045",
    "exchangeTradeId": "15112111182045",
    "transactionType": "BUY",
    "exchangeSegment": "NSE_EQ",
    "productType": "INTRADAY",
    "orderType": "LIMIT",
    "tradingSymbol": "TCS",
    "securityId": "11536",
    "tradedQuantity": 40,
    "tradedPrice": 3345.8,
    "createTime": "2021-03-10 11:20:06",
    "updateTime": "2021-11-25 17:35:12",
    "exchangeTime": "2021-11-25 17:35:12",
    "drvExpiryDate": null,
    "drvOptionType": null,
    "drvStrikePrice": 0.0
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| dhanClientId | string | User specific identification generated by Dhan |
| orderId | string | Order specific identification generated by Dhan |
| exchangeOrderId | string | Order specific identification generated by exchange |
| exchangeTradeId | string | Trade specific identification generated by exchange |
| transactionType | enum string | The trading side of transaction  `BUY` `SELL` |
| exchangeSegment | enum string | Exchange Segment of instrument to be subscribed as found in [Annexure](/docs/v2/annexure/#exchange-segment) |
| productType | enum string | Product type of trade `CNC`  `INTRADAY` `MARGIN` `MTF`  `CO` `BO` |
| orderType | enum string | Order Type  `LIMIT`  `MARKET`  `STOP_LOSS`  `STOP_LOSS_MARKET` |
| tradingSymbol | string | Refer Trading Symbol in Tables |
| securityId | string | Exchange standard ID for each scrip. Refer [here](/docs/v2/instruments/) |
| tradedQuantity | int | Number of shares executed |
| tradedPrice | float | Price at which trade is executed |
| createTime | string | Time at which the order is created |
| updateTime | string | Time at which the last activity happened |
| exchangeTime | string | Time at which order reached at exchange |
| drvExpiryDate | string | For F&O, expiry date of contract |
| drvOptionType | enum string | Type of Option   `CALL` `PUT` |
| drvStrikePrice | float | For Options, Strike Price |

Note: For description of enum values, refer [Annexure](https://dhanhq.co/docs/v2/annexure)

---


# Source: https://dhanhq.co/docs/v2/super-order/

# Super Order

Super orders are built for smart execution of your trades. They are a collection of orders clubbed into single order request, which includes entry leg, target leg and stop loss leg along with the option to add trailing stop loss.

This particular set of APIs can be used to create, modify and cancel super orders. You can place super orders across all exchanges and segments.

|  |  |  |
| --- | --- | --- |
| POST | /super/orders | Create a new super order |
| PUT | /super/orders/{order-id} | Modify a pending super order |
| DELETE | /super/orders/{order-id}/{order-leg} | Cancel a pending super order leg |
| GET | /super/orders | Retrieve the list of all super orders |

## Place Super Order

The super order request API lets you place new super orders. You can place a combination of orders using this API, wether that be entry leg, target leg and stop loss leg.

This order type is available across segments and exchanges. You can place intraday, carry forward or even MTF orders via this order type.

This API requires Static IP whitelisting - [here](/docs/v2/authentication/#setup-static-ip)

```python
    curl --request POST \
    --url https://api.dhan.co/v2/super/orders \
    --header 'Content-Type: application/json' \
    --header 'access-token: JWT' \
    --data '{Request JSON}'
```

**Request Structure**

```python
{
    "dhanClientId": "1000000003",
    "correlationId": "123abc678",
    "transactionType": "BUY",
    "exchangeSegment": "NSE_EQ",
    "productType": "CNC",
    "orderType": "LIMIT",
    "securityId": "11536",
    "quantity": 5,
    "price": 1500,
    "targetPrice": 1600,
    "stopLossPrice": 1400,
    "trailingJump": 10
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| dhanClientId   *required* | string | User specific identification generated by Dhan |
| correlationId | string | The user/partner generated id for tracking back |
| transactionType   *required* | enum string | The trading side of transaction   `BUY`  `SELL` |
| exchangeSegment   *required* | enum string | Exchange Segment of instrument to be subscribed as found in [Annexure](/docs/v2/annexure/#exchange-segment) |
| productType   *required* | enum string | Product type `CNC`  `INTRADAY` `MARGIN` `MTF` |
| orderType  *required* | enum string | Order Type  `LIMIT`  `MARKET` |
| securityId  *required* | string | Exchange standard ID for each scrip. Refer [here](/docs/v2/instruments/) |
| quantity *required* | int | Number of shares for the order |
| price  *required* | float | Price at which order is placed |
| targetPrice  *required* | float | Target Price for the Super Order |
| stopLossPrice *required* | float | Stop Loss Price for the Super Order |
| trailingJump *required* | float | Price Jump by which Stop Loss should be trailed |

**Response Structure**

```python
{
    "orderId": "112111182198",
    "orderStatus": "PENDING",
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| orderId | string | Order specific identification generated by Dhan |
| orderStatus | enum string | Last updated status of the order   `TRANSIT` `PENDING` `REJECTED` |

## Modify Super Order

This API can be used to modify any leg of a Super Order till it is in `PENDING` or `PART_TRADED` state.

Note

Order Entry Leg `ENTRY_LEG` can help modify the entire super order and can only be modified when the order status is `PENDING` or `PART_TRADED`. Once the entry order status is `TRADED`, only `TARGET_LEG` and `STOP_LOSS_LEG` price and trail jump can be modified.

This API requires Static IP whitelisting - [here](/docs/v2/authentication/#setup-static-ip)

```python
    curl --request PUT \
    --url https://api.dhan.co/v2/super/orders/{order-id} \
    --header 'Content-Type: application/json' \
    --header 'access-token: JWT' \
    --data '{Request JSON}'
```

**Request Structure**

Entry LegTargetStop Loss

```python
{
    "dhanClientId":"1000000009",
    "orderId":"112111182045",
    "orderType":"LIMIT",
    "legName":"ENTRY_LEG",
    "quantity":"40",
    "price":"1300",
    "targetPrice": 1450,
    "stopLossPrice": 1350,
    "trailingJump": 20
}
```

```python
{
    "dhanClientId":"1000000009",
    "orderId":"112111182045",
    "legName":"TARGET_LEG",
    "targetPrice": 1450
}
```

```python
{
    "dhanClientId":"1000000009",
    "orderId":"112111182045",
    "legName":"STOP_LOSS_LEG",
    "stopLossPrice": 1350,
    "trailingJump": 20
}
```

**Parameters**

| Field | Type | description |
| --- | --- | --- |
| dhanClientId    *required* | string | User specific identification generated by Dhan |
| orderId    *required* | string | Order specific identification generated by Dhan |
| orderType   *conditionally required* | enum string | Order Type   `LIMIT` `MARKET` |
| legName   *required* | enum string | `ENTRY_LEG` - Entire Super Order can be modified, only when main order status is `PENDING` or `PART\_TRADED`   `TARGET_LEG` `STOP_LOSS_LEG` |
| quantity *conditionally required* | int | Quantity to be modified - only for `ENTRY_LEG` |
| price   *conditionally required* | float | Price to be modified - only for `ENTRY_LEG` |
| targetPrice *conditionally required* | float | Target Price to be modified - `ENTRY_LEG` or `TARGET_LEG` |
| stopLossPrice *conditionally required* | float | Stop Loss Price to be modified - `ENTRY_LEG` or `STOP_LOSS_LEG` |
| trailingJump *conditionally required* | float | Stop Loss Price jump to be modified - `ENTRY_LEG` or `STOP_LOSS_LEG`  If trailing jump is not added or passed as `0`, it will be cancelled |

**Response Structure**

```python
{
    "orderId": "112111182045",
    "orderStatus": "TRANSIT"
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| orderId | string | Order specific identification generated by Dhan |
| orderStatus | enum string | Last updated status of the order   `TRANSIT` `PENDING` `REJECTED` `TRADED` |

## Cancel Super Order

Users can cancel a pending/active super order using the order ID. There is no
body for request and response for this call. On successful completion of
request ‘202 Accepted’ response status code will appear.

This API requires Static IP whitelisting - [here](/docs/v2/authentication/#setup-static-ip)

```python
    curl --request DELETE \
    --url https://api.dhan.co/v2/super/orders/{order-id}/{order-leg} \
    --header 'Content-Type: application/json' \
    --header 'access-token: JWT'
```

**Path Parameters**

| Field | Description | Example |
| --- | --- | --- |
| order-id   *required* | Order ID of the Order being cancelled | 11211182198 |
| order-leg   *required* | Order Leg to be cancelled | `ENTRY_LEG` `TARGET_LEG` `STOP_LOSS_LEG` |

> Note: Cancelling main order ID cancels all legs. If particular target or stop loss leg is cancelled, then the same cannot be added again.

**Response Structure**

```python
{
"orderId": "112111182045",
"orderStatus": "CANCELLED"
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| orderId | string | Order specific identification generated by Dhan |
| orderStatus | enum string | Last updated status of the order   `TRANSIT` `PENDING` `REJECTED` `CANCELLED` |

## Super Order List

This API lets you retrieve an array of all super orders placed in a day with their last updated status. This is a special order book which only consists of Super Orders, where the target and stop loss orders are nested under the main entry order leg. Individual legs of each super order can also be found in the main order book with their Order ID.

```python
    curl --request GET \
    --url https://api.dhan.co/v2/super/orders \
    --header 'Content-Type: application/json' \
    --header 'access-token: JWT'
```

**Request Structure**

*No Body*

**Response Structure**

```python
[
    {
        "dhanClientId": "1100003626",
        "orderId": "5925022734212",
        "correlationId": "string",
        "orderStatus": "PENDING",
        "transactionType": "BUY",
        "exchangeSegment": "NSE_EQ",
        "productType": "CNC",
        "orderType": "LIMIT",
        "validity": "DAY",
        "tradingSymbol": "HDFCBANK",
        "securityId": "1333",
        "quantity": 10,
        "remainingQuantity": 10,
        "ltp": 1660.95,
        "price": 1500,
        "afterMarketOrder": false,
        "legName": "ENTRY_LEG",
        "exchangeOrderId": "11925022734212",
        "createTime": "2025-02-27 19:09:42",
        "updateTime": "2025-02-27 19:09:42",
        "exchangeTime": "2025-02-27 19:09:42",
        "omsErrorDescription": "",
        "averageTradedPrice": 0,
        "filledQty": 0,
        "legDetails": [
            {
                "orderId": "5925022734212",
                "legName": "STOP_LOSS_LEG",
                "transactionType": "SELL",
                "totalQuatity": 0,
                "remainingQuantity": 0,
                "triggeredQuantity": 0,
                "price": 1400,
                "orderStatus": "PENDING",
                "trailingJump": 10
            },
            {
                "orderId": "5925022734212",
                "legName": "TARGET_LEG",
                "transactionType": "SELL",
                "remainingQuantity": 0,
                "triggeredQuantity": 0,
                "price": 1550,
                "orderStatus": "PENDING",
                "trailingJump": 0
            }
        ]
    }
]
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| dhanClientId | string | User specific identification generated by Dhan |
| orderId | string | Order specific identification generated by Dhan |
| correlationId | string | The user/partner generated id for tracking back |
| orderStatus | enum string | Last updated status of the order   `TRANSIT` `PENDING` `CLOSED` `REJECTED` `CANCELLED` `PART_TRADED` `TRADED` |
| transactionType | enum string | The trading side of transaction   `BUY` `SELL` |
| exchangeSegment | enum string | Exchange Segment of instrument to be subscribed as found in [Annexure](/docs/v2/annexure/#exchange-segment) |
| productType | enum string | Product type of trade `CNC`  `INTRADAY` `MARGIN` `MTF` |
| orderType | enum string | Order Type  `LIMIT`  `MARKET` |
| validity | enum string | Validity of Order  `DAY` |
| tradingSymbol | string | Refer Trading Symbol in Tables |
| securityId | string | Exchange standard ID for each scrip. Refer [here](/docs/v2/instruments/) |
| quantity | int | Number of shares for the order |
| remainingQuantity | int | Quantity pending execution |
| ltp | float | Last Traded Price of the instrument |
| price | float | Price at which order is placed |
| afterMarketOrder | boolean | If the order is placed after market |
| legName | enum string | Leg identification in case of BO   `ENTRY_LEG` `TARGET_LEG` `STOP_LOSS_LEG` |
| trailingJump | float | Price Jump by which Stop Loss should be trailed |
| exchangeOrderId | string | Exchange generated ID for the order |
| createTime | string | Time at which the order is created |
| updateTime | string | Last updated time of the order |
| exchangeTime | string | Time at which order was sent to the exchange |
| omsErrorDescription | string | Description of error in case the order is rejected or failed |
| remainingQuantity | integer | Quantity pending at the exchange to be traded (quantity - filledQty) |
| averageTradedPrice | integer | Average price at which order is traded |
| filledQty | integer | Quantity of order traded on Exchange |
| triggeredQuantity | integer | Quantity of Stop Loss or Target legs which has been placed on Exchange |
| legDetails | []array | Array of Leg Details |

Note

There are two order status updates that needs to be considered. `CLOSED` is used when the ENTRY\_LEG and one of either TARGET\_LEG or STOP\_LOSS\_LEG is also triggered for entire quantity. `TRIGGERED` is present for TARGET\_LEG and STOP\_LOSS\_LEG which indicates which of the two is actually triggered and then `triggeredQuantity` can be referred to check the placed quantity.

Note: For description of enum values, refer [Annexure](https://dhanhq.co/docs/v2/annexure)

---


# Source: https://dhanhq.co/docs/v2/forever/

# Forever Order

Users can create and manage Forever Orders or Good Till Triggered orders using this set of APIs.

REST

|  |  |  |
| --- | --- | --- |
| POST | /forever/orders | Create Forever Order |
| PUT | /forever/orders/{order-id} | Modify existing Forever Order |
| DELETE | /forever/orders/{order-id} | Cancel existing Forever Order |
| GET | /forever/orders | Retrieve an array of all existing forever orders |

Order Placement, Modification and Cancellation APIs requires Static IP whitelisting - [here](/docs/v2/authentication/#setup-static-ip)

## Create Forever Order

This API helps you create a new Forever Order.

cURL

```python
    curl --request POST \
    --url https://api.dhan.co/v2/forever/orders \
    --header 'Accept: application/json' \
    --header 'Content-Type: application/json' \
    --header 'access-token: ' \
    --data '{Request JSON}'
```

**Request structure**

cURL

```python
{
    "dhanClientId": "1000000132",
    "correlationId": "",
    "orderFlag": "OCO",
    "transactionType": "BUY",
    "exchangeSegment": "NSE_EQ",
    "productType": "CNC",
    "orderType": "LIMIT"
    "validity": "DAY",
    "securityId": "1333",
    "quantity": 5,
    "disclosedQuantity": 1,
    "price": 1428,
    "triggerPrice": 1427,
    "price1": 1420,
    "triggerPrice1": 1419,
    "quantity1": 10
}
```

**Parameters**

cURL

| Field | Type | Description |
| --- | --- | --- |
| dhanClientId *required* | string | User specific identification generated by Dhan |
| correlationId | string | The user/partner generated id for tracking back |
| orderFlag  *required* | string | Order Flag OCO for OCO order and SINGLE for Forever Order  `SINGLE` `OCO` |
| transactionType  *required* | string | The trading side of transaction   `BUY`  `SELL` |
| exchangeSegment  *required* | string | Exchange & Segment  `NSE_EQ`  `NSE_FNO`   `BSE_EQ`  `NSE_FNO` |
| productType *required* | string | Product type  `CNC`  `MTF` |
| orderType *required* | enum string | Order Type  `LIMIT`  `MARKET` |
| validity *required* | string | Validity of Order for execution  `DAY` `IOC` |
| securityId *required* | string | Exchange standard ID for each scrip. Refer [here](/docs/v2/instruments/) |
| quantity *required* | int | Number of shares for the order |
| disclosedQuantity | int | Number of shares visible (Keep more than 30% of quantity) |
| price *required* | float | Price at which order is placed |
| triggerPrice *required* | float | Price at which order is to be triggered |
| price1 *conditionally required* | float | Target price for OCO order |
| triggerPrice1 *conditionally required* | float | Target trigger price For OCO order |
| quantity1 *conditionally required* | integer | Target Quantity for OCO order |

**Response Structure**

```python
{
    "orderId": "5132208051112",
    "orderStatus": "PENDING"
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| orderId | string | Order specific identification generated by Dhan |
| orderStatus | string | Order Status  `TRANSIT`  `PENDING`  `REJECTED`  `CANCELLED`  `TRADED`  `EXPIRED`  `CONFIRM` |

## Modify Forever Order

Users can take use of this API to make changes to already created forever orders. The variables that can be modified are price, quantity, order type, disclosed quantity, trigger price & validity.

cURL

```python
curl --request PUT \
--url https://api.dhan.co/v2/forever/orders/{order-id} \
--header 'Accept: application/json' \
--header 'Content-Type: application/json' \
--header 'access-token: adad' \
--data '{Request JSON}'
```

**Requested Structure**

cURL

```python
{
    "dhanClientId": "1000000132",
    "orderId": "5132208051112",
    "orderFlag": "SINGLE",
    "orderType": "LIMIT",
    "legName": "TARGET_LEG",
    "quantity": 15,
    "price": 1421,
    "disclosedQuantity":1,
    "triggerPrice": 1420,
    "validity": "DAY"
}
```

**Parameters**

cURL

| Field | Type | Description |
| --- | --- | --- |
| dhanClientId  *required* | string | User specific identification generated by Dhan |
| orderId *required* | enum string | Order specific identification generated by Dhan |
| orderFlag   *required* | string | Order Flag OCO for OCO order and SINGLE for Forever Order  `SINGLE` `OCO` |
| orderType  *required* | enum string | Order Type  `LIMIT`  `MARKET`  `STOP_LOSS`  `STOP_LOSS_MARKET` |
| legName  *required* | string | Order leg of Forever Order where modification is to be done  `TARGET_LEG` - For Single and First leg of OCO   `STOP_LOSS_LEG` - For Second leg of OCO |
| quantity  *required* | int | Number of shares for the order |
| price  *required* | float | Price at which order is placed |
| disclosedQuantity | int | Number of shares visible (Keep more than 30% of quantity) |
| triggerPrice   *required* | float | Price at which order is to be triggered |
| validity  *required* | string | Validity of Order for execution  `DAY` `IOC` |

**Response Structure**

```python
{
    "orderId": "5132208051112",
    "orderStatus": "PENDING"
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| orderId | string | Order specific identification generated by Dhan |
| orderStatus | string | Last updated status of the order  `TRANSIT`  `PENDING`  `REJECTED`  `CANCELLED`  `TRADED`  `EXPIRED`  `CONFIRM` |

## Delete Forever Order

This API lets you delete pending Forever Order using the Order ID.

cURL

```python
curl --request DELETE \
--url https://api.dhan.co/v2/forever/orders/{order-id} \
--header 'Accept: application/json' \
--header 'access-token: {JWT}'
```

**Request Structure**

*No Body*

**Response Structure**

```python
{
    "orderId": "5132208051112",
    "orderStatus": "CANCELLED"
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| orderId | string | Order specific identification generated by Dhan |
| orderStatus | string | Order Status  `TRANSIT`  `PENDING`  `REJECTED`  `CANCELLED`  `TRADED`  `EXPIRED`  `CONFIRM` |

## All Forever Order Detail

Users can retrieve an array of all existing Forever Orders in their account using this API.

cURL

```python
curl --request GET \
--url https://api.dhan.co/v2/forever/all \
--header 'Accept: application/json' \
--header 'access-token: {JWT}' \
```

**Request Structure**

*No Body*

**Response Structure**

```python
[
    {
        "dhanClientId": "1000000132",
        "orderId": "1132208051115",
        "orderStatus": "CONFIRM",
        "transactionType": "BUY",
        "exchangeSegment": "NSE_EQ",
        "productType": "CNC",
        "orderType": "SINGLE",
        "tradingSymbol": "HDFCBANK",
        "securityId": "1333",
        "quantity": 10,
        "price": 1428,
        "triggerPrice": 1427,
        "legName": "ENTRY_LEG",
        "createTime": "2022-08-05 12:41:19",
        "updateTime": null,
        "exchangeTime": null,
        "drvExpiryDate": null,
        "drvOptionType": null,
        "drvStrikePrice": 0
    }
]
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| dhanClientId | string | User specific identification generated by Dhan |
| orderId | string | Order specific identification generated by Dhan |
| orderStatus | enum string | Last updated status of the order  `TRANSIT` `PENDING` `REJECTED` `CANCELLED` `TRADED` `EXPIRED` `CONFIRM` |
| transactionType | enum string | The trading side of transaction  `BUY` `SELL` |
| exchangeSegment | enum string | Exchange & Segment   `NSE_EQ`  `NSE_FNO`   `BSE_EQ`  `MCX_COMM` |
| productType | enum string | Product type of trade `CNC`  `INTRADAY`  `MARGIN`  `CO` `BO` |
| orderType | enum string | Order Type  `SINGLE`  `OCO` |
| tradingSymbol | string | Symbol of the instrument in which forever order is placed |
| securityId | string | Exchange standard ID for each scrip. Refer [here](/docs/v2/instruments/) |
| quantity | int | Number of shares for the order |
| price | float | Price at which order is placed |
| triggerPrice | float | Price at which order is to be triggered |
| legName | string | Order leg of Forever Order  `TARGET_LEG` - For Single and First leg of OCO  `STOP_LOSS_LEG` - For Second leg of OCO |
| createTime | string | Time at which the Forever Order is created |
| updateTime | string | Time at which the Forever Order is updated |
| exchangeTime | string | Time at which order reached at exchange end |
| drvExpiryDate | string | Contract Expiry Date for Derivative contract |
| drvOptionType | enum string | Type of Option `CALL`  `PUT` |
| drvStrikePrice | float | Strike Price in case of Option Contract |

Note: For description of enum values, refer [Annexure](https://dhanhq.co/docs/v2/annexure)

---


# Source: https://dhanhq.co/docs/v2/portfolio/

# Portfolio

This API lets you retrieve holdings and positions in your portfolio.

|  |  |  |
| --- | --- | --- |
| GET | /holdings | Retrieve list of holdings in demat account |
| GET | /positions | Retrieve open positions |
| POST | /positions/convert | Convert intraday position to delivery or delivery to intraday |

## Holdings

Users can retrieve all holdings bought/sold in previous trading sessions. All T1 and delivered quantities can be fetched.

```python
    curl --request GET \
    --url https://api.dhan.co/v2/holdings \
    --header 'Content-Type: application/json' \
    --header 'access-token: JWT'
```

**Request Structure**

*No Body*

**Response Structure**

```python
[
    {
    "exchange": "ALL",
    "tradingSymbol": "HDFC",
    "securityId": "1330",
    "isin": "INE001A01036",
    "totalQty": 1000,
    "dpQty": 1000,
    "t1Qty": 0,
    "availableQty": 1000,
    "collateralQty": 0,
    "avgCostPrice": 2655.0
    } 
]
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| exchange | enum string | Exchange |
| tradingSymbol | string | Refer Trading Symbol at Page No |
| securityId | string | Exchange standard ID for each scrip. Refer [here](/docs/v2/instruments/) |
| isin | string | Universal standard ID for each scrip |
| totalQty | int | Total quantity |
| dpQty | int | Quantity delivered in demat account |
| t1Qty | int | Quantity pending delivered in demat account |
| availableQty | int | Quantity available for transaction |
| collateralQty | int | Quantity placed as collateral with broker |
| avgCostPrice | float | Average Buy Price of total quantity |

## Positions

Users can retrieve a list of all open positions for the day. This includes all F&O carryforward positions as well.

```python
    curl --request GET \
    --url https://api.dhan.co/v2/positions \
    --header 'Content-Type: application/json' \
    --header 'access-token: JWT'
```

**Request Structure**

*No Body*

**Response Structure**

```python
[
    {
    "dhanClientId": "1000000009",    
    "tradingSymbol": "TCS",
    "securityId": "11536",
    "positionType": "LONG",
    "exchangeSegment": "NSE_EQ", 
    "productType": "CNC",
    "buyAvg": 3345.8,
    "buyQty": 40,
    "costPrice": 3215.0,
    "sellAvg": 0.0,
    "sellQty": 0,
    "netQty": 40,
    "realizedProfit": 0.0,
    "unrealizedProfit": 6122.0,
    "rbiReferenceRate": 1.0,
    "multiplier": 1,
    "carryForwardBuyQty": 0,
    "carryForwardSellQty": 0,
    "carryForwardBuyValue": 0.0,
    "carryForwardSellValue": 0.0,
    "dayBuyQty": 40,
    "daySellQty": 0,
    "dayBuyValue": 133832.0,
    "daySellValue": 0.0,
    "drvExpiryDate": "0001-01-01",
    "drvOptionType": null,
    "drvStrikePrice": 0.0.
    "crossCurrency": false
    } 
]
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| dhanClientId | string | User specific identification generated by Dhan |
| tradingSymbol | string | Refer Trading Symbol in Tables |
| securityId | string | Exchange standard id for each scrip. Refer [here](/docs/v2/instruments/) |
| positionType | enum string | Position Type   `LONG` `SHORT` `CLOSED` |
| exchangeSegment | enum string | Exchange & Segment  `NSE_EQ` `NSE_FNO` `NSE_CURRENCY` `BSE_EQ` `BSE_FNO` `BSE_CURRENCY` `MCX_COMM` |
| productType | enum string | Product type `CNC`  `INTRADAY` `MARGIN` `MTF`  `CO` `BO` |
| buyAvg | float | Average buy price mark to market |
| buyQty | int | Total quantity bought |
| costPrice | int | Actual Cost Price |
| sellAvg | float | Average sell price mark to market |
| sellQty | int | Total quantities sold |
| netQty | int | buyQty - sellQty = netQty |
| realizedProfit | float | Profit or loss booked |
| unrealizedProfit | float | Profit or loss standing for open position |
| rbiReferenceRate | float | RBI mandated reference rate for forex |
| multiplier | int | Multiplying factor for currency F&O |
| carryForwardBuyQty | int | Carry forward F&O long quantities |
| carryForwardSellQty | int | Carry forward F&O short quantities |
| carryForwardBuyValue | float | Carry forward F&O long value |
| carryForwardSellValue | float | Carry forward F&O short value |
| dayBuyQty | int | Quantities bought today |
| daySellQty | int | Quantities sold today |
| dayBuyValue | float | Value of quantities bought today |
| daySellValue | float | Value of quantities sold today |
| drvExpiryDate | string | For F&O, expiry date of contract |
| drvOptionType | enum string | Type of Option  `CALL` `PUT` |
| drvStrikePrice | float | For Options, Strike Price |
| crossCurrency | boolean | Check for non INR currency pair |

## Convert Position

Users can convert their open position from intraday to delivery or delivery to intraday.

```python
curl --request POST \
--url https://api.dhan.co/v2/positions/convert \
--header 'Accept: application/json' \
--header 'Content-Type: application/json' \
--header 'access-token: JWT' \
--data '{}'
```

**Request Structure**

```python
{
    "dhanClientId": "1000000009",
    "fromProductType":"INTRADAY",  
    "exchangeSegment":"NSE_EQ",
    "positionType":"LONG",
    "securityId":"11536",  
    "tradingSymbol":"",
    "convertQty":"40",
    "toProductType":"CNC"
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| dhanClientId | string | User specific identification generated by Dhan |
| fromProductType | enum string | Refer Trading Symbol in Tables  `CNC` `INTRADAY` `MARGIN` `CO` `BO` |
| exchangeSegment | enum string | Exchange & segment in which position is created - [here](/docs/v2/annexure/#exchange-segment) |
| positionType | enum string | Position Type  `LONG` `SHORT` `CLOSED` |
| securityId | string | Exchange standard id for each scrip. Refer [here](/docs/v2/instruments/) |
| tradingSymbol | string | Refer Trading Symbol in Tables |
| convertQty | int | No of shares modification is desired |
| toProductType | enum string | Desired product type `CNC`  `INTRADAY` `MARGIN` `CO` `BO` |

**Response Structure**

```python
202 Accepted
```

Note: For description of enum values, refer [Annexure](https://dhanhq.co/docs/v2/annexure)

---


# Source: https://dhanhq.co/docs/v2/edis/

# EDIS

To sell holding stocks, one needs to complete the CDSL eDIS flow, generate T-PIN & mark stock to complete the sell action.

|  |  |  |
| --- | --- | --- |
| GET | /edis/tpin | Generate T-PIN |
| POST | /edis/from | Retrieve escaped html form & enter T-PIN |
| GET | /edis/inquire/{isin} | Inquire the status of stock for edis approval. |

## Generate T-PIN

Get T-Pin on your registered mobile number using this API.

```python
    curl --request GET \
    --url https://api.dhan.co/v2/edis/tpin \
    --header 'Content-Type: application/json' \
    --header 'access-token: JWT'
```

Request Structure

*No Body*

**Response Structure**

```python
202 Accepted
```

## Generate eDIS Form

Retrieve escaped html form of CDSL and enter T-PIN to mark the stock for EDIS approval. User has to render this form at their end to unescape.
You can get ISIN of portfolio stocks, in response of holdings API.

```python
    curl --request POST \
    --url https://api.dhan.co/v2/edis/form \
    --header 'Content-Type: application/json' \
    --header 'access-token: ' \
    --data '{}'
```

**Request Structure**

```python
    {
        "isin": "INE733E01010",  
        "qty": 1,
        "exchange": "NSE",
        "segment": "EQ",
        "bulk": true
    }
```

**Parameters**

| Field | Field Type | Description |
| --- | --- | --- |
| isin | string | International Securities Identification Number |
| qty | int | Number of shares to mark for edis transaction |
| exchange | string | Exhange `NSE` `BSE` |
| segment | string | Segment `EQ` |
| bulk | boolean | To mark edis for all stocks in portfolio |

**Response Structure**

```python
{
    "dhanClientId": "1000000401",
    "edisFormHtml": "<!DOCTYPE html> <html>     <script>window.onload= function()
        {submit()};function submit(){ document.getElementById(\"submitbtn\").click();    }
        </script><body onload=\"submit()\">     <form name=\"frmDIS\" method=\"post\" 
        action=\"https://edis.cdslindia.com/eDIS/VerifyDIS/\" style=\"                
        text-align: center; margin-top: 35px; /* margin-bottom: 15px; */ \">             
        <input type= \"hidden\" name= \"DPId\" value= \"83400\" >  
        <input type= \"hidden\" name= \"ReqId\" value= \"291951000000401\" >             
        <input type= \"hidden\" name= \"Version\" value= \"1.1\" >             
        <input type= \"hidden\" name= \"TransDtls\" value= \"kQBOKYtPSbWmbLYOih9ZXaLZuA3Ig5ycFPangwWZKTPgmIqdfXL58qN3tGfDlVH+S613mfqTkIWVkQTiMrqUHkzvTRxkr7NtJtP7O3Z7+Xro9Fs5svt2tQDrNJGSd1oEqc4dhoc+FCS8u9ZhNCFqkZ30djjKqjTp1j12fv4cZVwzupyLfVVyh0U8TwwqSAEP4mdq3uiimxADlrHVRrn5NSL+ndUn5BhplI7F9Ksiscj9hxz6iK2Os8m5JMFBU7bmNmIWWHEgTLOz0N+roldjRs2M8mVXSx+M+41jrdSWaCnMxvm+L2HNbsT94Zv8wEWmxSCcSDcvVFhbpcWP5RVQMHQpV6cw6+s7qfn1AWexGiUJk3APPnhYdXPjwIewhyL5rEhNRnCy+cZaJSzsBpatfOJO3xjrZd6zDv6raf/4EUwHJ8yOVYjG5L4uAjnsfBy0SCuqYnxmMphI8/mnJlopH71Kvi9IkH/wPBiKvOkNYpJD3+CFXE6No3RrRiC8DF1pkSaMm7IxdHr0ui2QBmyqcg==\" >  
        <input style=\"display: none;\" id=\"submitbtn\" type= \"submit\" value=\"Submit\">     
        </form> </body> </html>"
}
```

**Parameters**

|  |  |  |
| --- | --- | --- |
| Field | Field type | Description |
| dhanClientId | string | User specific identification generated by Dhan |
| edisFormHtml | string | Escaped HTML Form |

## EDIS Status & Inquiry

You can check the status of stock whether it is approved and marked for sell action. User have to enter ISIN of the stock.
An International Securities Identification Number (ISIN) is a 12-digit alphanumeric code that uniquely identifies a specific security.
You can get ISIN of portfolio stocks, in response of holdings API.   
  
Alternatively, you can pass "ALL" instead of ISIN to get eDIS status of all holdings in your portfolio.

cURLPython

```python
curl --request GET \
--url https://api.dhan.co/v2/edis/inquire/{isin} \
--header 'Content-Type: application/json' \
--header 'access-token: JWT'
```

```python
dhan.edis_inquiry(isin)
```

**Request Structure**

*No Body*

**Response Structure**

```python
{
    "clientId": "1000000401",
    "isin": "INE00IN01015",
    "totalQty": 10,
    "aprvdQty": 4,
    "status": "SUCCESS",
    "remarks": "eDIS transaction done successfully"
}
```

**Parameters**

| Field | Field type | Description |
| --- | --- | --- |
| clientId | string | User specific identification |
| isin | string | International Securities Identification Number |
| totalQty | string | Total number of shares for given stock |
| aprvdQty | string | Number of approved stocks |
| status | string | Status of the edis order |
| remark | string | remarks of the order status |

Note: For description of enum values, refer [Annexure](https://dhanhq.co/docs/v2/annexure)

---


# Source: https://dhanhq.co/docs/v2/traders-control/

# Trader's Control

## Kill Switch

This API lets you activate the kill switch for your account, which will disable trading for current trading day. You can pass header parameter as `ACTIVATE` or `DEACTIVATE` to manage Kill Switch settings.

Note

You need to ensure that all your positions are closed and there are no pending orders in your account to be able to activate Kill Switch.

```python
curl --request POST \
--url 'https://api.dhan.co/v2/killswitch?killSwitchStatus=ACTIVATE' \
--header 'Accept: application/json' \
--header 'Content-Type: application/json' \
--header 'access-token: JWT'
```

**Request Structure**

*No Body*

**Response Structure**

```python
{
    "dhanClientId":"1000000009",
    "killSwitchStatus": "Kill Switch has been successfully activated"
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| dhanClientId | string | User specific identification generated by Dhan |
| killSwitchStatus | string | Status of Kill Switch - activated or not |

Note: For description of enum values, refer [Annexure](https://dhanhq.co/docs/v2/annexure)

---


# Source: https://dhanhq.co/docs/v2/funds/

# Funds

Users can get details about the fund requirements or available funds (with margin requirements) in their Trading Account.

|  |  |  |
| --- | --- | --- |
| POST | /margincalculator | Margin requirement for any order |
| GET | /fundlimit | Retrieve trading account fund information |

## Margin Calculator

Fetch span, exposure, var, brokerage, leverage, available margin values for any type of order and instrument that you want to place.

```python
    curl --request POST \
    --url https://api.dhan.co/v2/margincalculator \
    --header 'Accept: application/json' \
    --header 'Content-Type: application/json' \
    --header 'access-token: ' \
    --data '{Request JSON}'
```

**Request Structure**

cURL

```python
{
    "dhanClientId": "1000000132",
    "exchangeSegment": "NSE_EQ",
    "transactionType": "BUY",
    "quantity": 5,
    "productType": "CNC",
    "securityId": "1333",
    "price": 1428,
    "triggerPrice": 1427,
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| dhanClientId   *required* | string | User specific identification generated by Dhan |
| exchangeSegment   *required* | enum string | Exchange & Segment  `NSE_EQ` `NSE_FNO`  `BSE_EQ` `BSE_FNO`  `MCX_COMM` |
| transactionType   *required* | enum string | The trading side of transaction   `BUY`  `SELL` |
| quantity  *required* | int | Number of shares for the order |
| productType   *required* | enum string | Product type `CNC`  `INTRADAY` `MARGIN` `MTF`  `CO` `BO` |
| securityId  *required* | string | Exchange standard id for each scrip. Refer [here](/docs/v2/instruments/) |
| price  *required* | float | Price at which order is placed |
| triggerPrice  *conditionally required* | float | Price at which the order is triggered, in case of SL-M & SL-L |

**Response Structure**

```python
{
    "totalMargin": 2800.00,
    "spanMargin": 1200.00,
    "exposureMargin": 1003.00,
    "availableBalance": 10500.00,
    "variableMargin": 1000.00,
    "insufficientBalance": 0.00,
    "brokerage": 20.00,
    "leverage": "4.00"
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| totalMargin | float | Total Margin required for placing the order successfully |
| spanMargin | float | SPAN margin required |
| exposureMargin | float | Exposure margin required |
| availableBalance | float | Available amount in trading account |
| variableMargin | float | VAR or Variable margin required |
| insufficientBalance | float | Insufficient amount in trading account (Available Balance - Total Margin) |
| brokerage | float | Brokerage charges for executing order |
| leverage | string | Margin leverage provided for the order as per product type |

## Fund Limit

Get all information of your trading account like balance, margin utilised, collateral, etc.

```python
    curl --request GET \
    --url https://api.dhan.co/v2/fundlimit \
    --header 'Content-Type: application/json' \
    --header 'access-token: JWT'
```

**Request Structure**

*No Body*

**Response Structure**

```python
{
    "dhanClientId":"1000000009",
    "availabelBalance": 98440.0,
    "sodLimit": 113642,
    "collateralAmount": 0.0,
    "receiveableAmount": 0.0,
    "utilizedAmount": 15202.0,
    "blockedPayoutAmount": 0.0,
    "withdrawableBalance": 98310.0
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| dhanClientId | string | User specific identification generated by Dhan |
| availabelBalance | float | Available amount to trade |
| sodLimit | float | Start of the day balance in account |
| collateralAmount | float | Amount received against collateral |
| receiveableAmount | float | Amount available against selling deliveries |
| utilizedAmount | float | Amount utilised in the day |
| blockedPayoutAmount | float | Amount blocked against payout request |
| withdrawableBalance | float | Amount available to withdraw in bank account |

Note: For description of enum values, refer [Annexure](https://dhanhq.co/docs/v2/annexure)

---


# Source: https://dhanhq.co/docs/v2/statements/

# Statement

This set of APIs retreives all your trade and ledger details to help you summarise and analyse your trades.

|  |  |  |
| --- | --- | --- |
| GET | /ledger | Retrieve Trading Account debit and credit details |
| GET | /trades/ | Retrieve historical trade data |

## Ledger Report

Users can retrieve Trading Account Ledger Report with all Credit and Debit transaction details for a particular time interval. For this, you need to pass start date and end date as query parameters to define time interval of Ledger Report.

```python
curl --request GET \
--url 'https://api.dhan.co/v2/ledger?from-date={YYYY-MM-DD}&to-date={YYYY-MM-DD}' \
--header 'Accept: application/json' \
--header 'access-token: {JWT}'
```

**Query Parameters**

| Field | Description |
| --- | --- |
| from-date *required* | Date from which Ledger Report is required in format `YYYY-MM-DD` |
| to-date *required* | Date upto which Ledger Report is required in format `YYYY-MM-DD` |

**Request Structure**

*No Body*

**Response Structure**

```python
{
    "dhanClientId": "1000000001",
    "narration": "FUNDS WITHDRAWAL",
    "voucherdate": "Jun 22, 2022",
    "exchange": "NSE-CAPITAL",
    "voucherdesc": "PAYBNK",
    "vouchernumber": "202200036701",
    "debit": "20000.00",
    "credit": "0.00",
    "runbal": "957.29"
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| dhanClientId | string | User specific identification generated by Dhan |
| narration | string | Description of the ledger transaction |
| voucherdate | string | Transaction Date |
| exchange | string | Exchange information for the transaction |
| voucherdesc | string | Nature of transaction |
| vouchernumber | string | System generated transaction number |
| debit | string | Debit amount (only when credit returns 0) |
| credit | string | Credit amount (only when debit returns 0) |
| runbal | string | Running Balance post transaction |

## Trade History

Users can retrieve their detailed trade history for all orders for a particular time frame. User needs to add header parameters along with page number as the response is paginated.

```python
curl --request GET \
--url https://api.dhan.co/v2/trades/{from-date}/{to-date}/{page} \
--header 'Accept: application/json' \
--header 'access-token: {JWT}'
```

**Path Parameters**

| Field | Description |
| --- | --- |
| from-date *required* | Date from which Trade History is required in format `YYYY-MM-DD` |
| to-date *required* | Date upto which Trade History is required in format `YYYY-MM-DD` |
| page *required* | Page number of which data is being fetched. Pass `0` as default. |

**Request Structure**

*No Body*

**Response Structure**

```python
[
    {
    "dhanClientId": "1000000001",
    "orderId": "212212307731",
    "exchangeOrderId": "76036896",
    "exchangeTradeId": "407958",
    "transactionType": "BUY",
    "exchangeSegment": "NSE_EQ",
    "productType": "CNC",
    "orderType": "MARKET",
    "tradingSymbol": null,
    "customSymbol": "Tata Motors",
    "securityId": "3456",
    "tradedQuantity": 1,
    "tradedPrice": 390.9,
    "isin": "INE155A01022",
    "instrument": "EQUITY",
    "sebiTax": 0.0004,
    "stt": 0,
    "brokerageCharges": 0,
    "serviceTax": 0.0025,
    "exchangeTransactionCharges": 0.0135,
    "stampDuty": 0,
    "createTime": "NA",
    "updateTime": "NA",
    "exchangeTime": "2022-12-30 10:00:46",
    "drvExpiryDate": "NA",
    "drvOptionType": "NA",
    "drvStrikePrice": 0
    } 
]
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| dhanClientId | string | User specific identification generated by Dhan |
| orderId | string | Order specific identification generated by Dhan |
| exchangeOrderId | string | Order specific identification generated by exchange |
| exchangeTradeId | string | Trade specific identification generated by exchange |
| transactionType | enum string | The trading side of transaction  `BUY` `SELL` |
| exchangeSegment | enum string | Exchange Segment of instrument to be subscribed as found in [Annexure](/docs/v2/annexure/#exchange-segment) |
| productType | enum string | Product type of trade `CNC`  `INTRADAY` `MARGIN` `MTF`  `CO` `BO` |
| orderType | enum string | Order Type  `LIMIT`  `MARKET`  `STOP_LOSS`  `STOP_LOSS_MARKET` |
| tradingSymbol | string | Symbol in which order was placed - Refer [here](/docs/v2/instruments/) |
| customSymbol | string | Trading Symbol as per Dhan |
| securityId | string | Exchange standard ID for each scrip. Refer [here](/docs/v2/instruments/) |
| tradedQuantity | int | Number of shares executed |
| tradedPrice | float | Price at which trade is executed |
| isin | string | Universal standard ID for each scrip |
| instrument | string | Type of Instrument  `EQUITY` `DERIVATIVES` |
| sebiTax | string | SEBI Turnover Charges |
| stt | string | Securities Transactions Tax |
| brokerageCharges | string | Brokerage charges by Dhan, refer pricing [here](https://dhan.co/pricing/) |
| serviceTax | string | Applicable Service Tax |
| exchangeTransactionCharges | string | Exchange Transaction Charge |
| stampDuty | string | Stamp Duty Charges |
| createTime | string | Time at which the order is created |
| updateTime | string | Time at which the last activity happened |
| exchangeTime | string | Time at which order reached at exchange |
| drvExpiryDate | int | For F&O, expiry date of contract |
| drvOptionType | enum string | Type of Option   `CALL` `PUT` |
| drvStrikePrice | float | For Options, Strike Price |

Note: For description of enum values, refer [Annexure](https://dhanhq.co/docs/v2/annexure)

---


# Source: https://dhanhq.co/docs/v2/postback/

# Postback

Postback API or Webhooks uses a `POST` request with **JSON payload** to the Postback URL. This JSON payload contains order update in case of change in status
(`TRANSIT`,
`PENDING`,
`REJECTED`,
`CANCELLED`,
`TRADED` or
`EXPIRED`)
or whenever order is modified or partially filled.

This Postback API is on **access token** level i.e. all trades originating from one particular access token will be sent to that particular Webhook URL. This makes it optimal for individual developers.

### Postback Payload

The JSON payload is sent as a raw HTTP POST body in below structure.

**Structure**

```python
{
    "dhanClientId": "1000000003",
    "orderId": "112111182198",
    "correlationId":"123abc678",
    "orderStatus": "PENDING",
    "transactionType": "BUY",
    "exchangeSegment": "NSE_EQ",
    "productType": "INTRADAY",
    "orderType": "MARKET",
    "validity": "DAY",
    "tradingSymbol": "",
    "securityId": "11536",
    "quantity": 5,
    "disclosedQuantity": 0,
    "price": 0.0,
    "triggerPrice": 0.0,
    "afterMarketOrder": false,
    "boProfitValue": 0.0,
    "boStopLossValue": 0.0,
    "legName": ,
    "createTime": "2021-11-24 13:33:03",
    "updateTime": "2021-11-24 13:33:03",
    "exchangeTime": "2021-11-24 13:33:03",
    "drvExpiryDate": null,
    "drvOptionType": null,
    "drvStrikePrice": 0.0,
    "omsErrorCode": null,
    "omsErrorDescription": null,
    "filled_qty": 1,
    "algoId": null
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| dhanClientId | string | User specific identification generated by Dhan |
| orderId | string | Order specific identification generated by Dhan |
| correlationId | string | The user/partner generated id for tracking back |
| orderStatus | enum string | Last updated status of the order   `TRANSIT` `PENDING` `REJECTED` `CANCELLED` `TRADED` `EXPIRED` |
| transactionType | enum string | The trading side of transaction   `BUY` `SELL` |
| exchangeSegment | enum string | Exchange & Segment   `NSE_EQ`  `NSE_FNO`   `NSE_CURRENCY`  `BSE_EQ`  `MCX_COMM` |
| productType | enum string | Product type of trade `CNC`  `INTRADAY` `MARGIN` `MTF`  `CO` `BO` |
| orderType | enum string | Order Type  `LIMIT`  `MARKET`  `STOP_LOSS`  `STOP_LOSS_MARKET` |
| validity | enum string | Validity of Order  `DAY` `IOC` |
| tradingSymbol | string | Refer Trading Symbol in Tables |
| securityId | string | Exchange standard id for each scrip. Refer [here](/docs/v2/instruments/) |
| quantity | int | Number of shares for the order |
| disclosedQuantity | int | Number of shares visible |
| price | float | Price at which order is placed |
| triggerPrice | float | Price at which order is triggered, for SL-M, SL-L, CO & BO |
| afterMarketOrder | boolean | The order placed is AMO ? |
| boProfitValue | float | Bracket Order Target Price change |
| boStopLossValue | float | Bracket Order Stop Loss Price change |
| legName | enum string | Leg identification in case of BO   `ENTRY_LEG` `TARGET_LEG` `STOP_LOSS_LEG` |
| createTime | string | Time at which the order is created |
| updateTime | string | Time at which the last activity happened |
| exchangeTime | string | Time at which order reached at exchange |
| drvExpiryDate | string | For F&O, expiry date of contract |
| drvOptionType | enum string | Type of Option   `CALL` `PUT` |
| drvStrikePrice | float | For Options, Strike Price |
| omserroeCode | string | Error code in case the order is rejected or failed |
| omsErrorDescription | string | Description of error in case the order is rejected or failed |
| filled\_qty | int | Quantity which has already been traded |
| algoId | string | Algo ID registered with the Exchange, in case of registered algos |

### Setting up Postback

To set up Postback API, you will need to provide a unique Postback URL to receive callbacks. You will need to follow the steps below to set up Postback URL:

* While generating access token on [web.dhan.co](https://web.dhan.co), enter your URL in the 'Postback URL' field.
* Click on 'Generate' to successfully set Postback and generate a new token.

Important: You will not receive postback calls if Postback URL is set to `localhost` or `127.0.0.1`.

> Note: To receive Postback originating for all orders placed from a platform/app, [Partner Login](https://dhanhq.co/docs/v2/#for-partners) module needs to be used.

---


# Source: https://dhanhq.co/docs/v2/order-update/

# Live Order Update

Realtime order updates of all your orders can be received directly via WebSocket in your system. Once you connect to the WebSocket and authorise, all order updates in your acount will get reflected real time via the stream.

With this update stream, you can know about status, traded price, quantity and other details about your orders.

The messages sent over this WebSocket will be JSON.

### Establishing Connection

To establish connection with DhanHQ Live Order Update, you can connect to the below endpoint using WebSocket library.

```python
wss://api-order-update.dhan.co
```

While establishing connection, you need to send Authorisation Message for connection.

#### For Individual

You can receive order updates for all orders placed via your account, irrespective of the platform via which it was placed.

**Authorisation message structure**

```python
{
    "LoginReq":{
        "MsgCode": 42,
        "ClientId":"1000000001",
        "Token":"JWT"
    },
    "UserType: "SELF"
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| LoginReq *required* | {}, string | JSON for adding Client ID and Access Token |
| MsgCode *required* | int | Message Code for getting Order Updates  `42` by default |
| ClientId *required* | string | User specific identification generated by Dhan |
| Token *required* | string | Access Token generated for user |
| UserType *required* | string | `SELF` for individual users |

#### For Partners

Platforms can receive order updates originating for all users connected to their platform/app for which [Partner Login](https://dhanhq.co/docs/v2/#for-partners) module needs to be used.

**Authorisation message structure**

```python
{
    "LoginReq":{
        "MsgCode": 42,
        "ClientId": "partner_id"
    },
    "UserType: "PARTNER",
    "Secret": "partner_secret"
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| LoginReq *required* | {}, string | JSON for adding Client ID and Access Token |
| MsgCode *required* | int | Message Code for getting Order Updates  `42` by default |
| ClientId *required* | string | `partner_id` generated for the partner |
| UserType *required* | string | `PARTNER` for partner platforms |
| Secret *required* | string | `partner_secret` generated for the partner |

### Order Update

Order Update messages are sent via WebSocket in below structure.

**Structure**

```python
{
    "Data": {
        "series": "EQ",
        "goodTillDaysDate": "2024-09-11",
        "instrumentType": "EQ",
        "refLtp": 13.21,
        "tickSize": 0.01,
        "algoId": "0",
        "multiplier": 1
        "Exchange": "NSE",
        "Segment": "E",
        "Source": "N",
        "SecurityId": "14366",
        "ClientId": "1000000001",
        "ExchOrderNo": "1400000000404591",
        "OrderNo": "1124091136546",
        "Product": "C",
        "TxnType": "B",
        "OrderType": "LMT",
        "Validity": "DAY",
        "DiscQuantity": 1,
        "DiscQtyRem": 1,
        "RemainingQuantity": 1,
        "Quantity": 1,
        "TradedQty": 0,
        "Price": 13,
        "TriggerPrice": 0,
        "TradedPrice": 0,
        "AvgTradedPrice": 0,
        "AlgoOrdNo": ,
        "OffMktFlag": "0",
        "OrderDateTime": "2024-09-11 14:39:29",
        "ExchOrderTime": "2024-09-11 14:39:29",
        "LastUpdatedTime": "2024-09-11 14:39:29",
        "Remarks": "NR",
        "MktType": "NL",
        "ReasonDescription": "CONFIRMED",
        "LegNo": 1,
        "Instrument": "EQUITY",
        "Symbol": "IDEA",
        "ProductName": "CNC",
        "Status": "Cancelled",
        "LotSize": 1,
        "StrikePrice": ,
        "ExpiryDate": "0001-01-01 00:00:00",
        "OptType": "XX",
        "DisplayName": "Vodafone Idea",
        "Isin": "INE669E01016",
        "Series": "EQ",
        "GoodTillDaysDate": "2024-09-11",
        "RefLtp": 13.21,
        "TickSize": 0.01,
        "AlgoId": "0",
        "Multiplier": 1,
        "CorrelationId": "",
        "Remarks": "Super Order"
    },
    "Type": "order_alert"
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| Exchange | string | Exchange in which order is placed |
| Segment | string | Segment for which order is placed |
| Source | string | Platform via which order is placed - `P` for API Orders |
| SecurityId | string | Exchange standard ID for each scrip. Refer [here](/docs/v2/instruments/) |
| ClientId | string | User specific identification generated by Dhan |
| ExchOrderNo | string | Order specific identification generated by Exchange |
| OrderNo | string | Order specific identification generated by Dhan |
| Product | enum string | Product type of trade `C`  for CNC, `I`  for INTRADAY, `M`  for MARGIN, `F` for MTF  , `V` for CO,  `B` for BO |
| TxnType | enum string | The trading side of transaction   `B` for Buy   `S` for Sell |
| OrderType | enum string | Order Type  `LMT` for Limit   `MKT` for Market   `SL` for Stop Loss   `SLM` for Stop Loss |
| Validity | enum string | Validity of Order  `DAY` `IOC` |
| DiscQuantity | int | Number of shares visible |
| DiscQtyRem | int | Disclosed quantity pending for execution |
| RemainingQuantity | int | Quantity pending for execution |
| Quantity | int | Total order quantity placed |
| TradedQty | int | Actual quantity executed on exchange |
| Price | float | Price at which order is placed |
| TriggerPrice | float | Price at which order is triggered, for SL-M, SL-L, CO & BO |
| TradedPrice | float | Price at which trade of an order is executed |
| AvgTradedPrice | float | Average trade price of an order (this will be different from `Traded Price` in case of partial execution) |
| AlgoOrdNo | float | Entry leg order number to track Target and Stop Loss leg (in case of `BO` and `CO`) |
| OffMktFlag | string | `1` in case of AMO order else `0` |
| OrderDateTime | string | Time at which the order is received by Dhan |
| ExchOrderTime | string | Time at which order is placed on Exchange |
| LastUpdatedTime | string | Last update time of any order modification or trade |
| Remarks | string | Additional remarks sent along while placing order |
| MktType | string | `NL` for Normal Market  `AU`, `A1` and `A2`for Auction Market |
| ReasonDescription | string | Order rejection reason |
| LegNo | int | `1` for Entry Leg  `2` for Stop Loss Leg  `3` for Target Leg |
| Instrument | string | Instrument in which order is placed - [here](/docs/v2/annexure/#instrument) |
| Symbol | string | Symbol in which order is placed - Refer [here](/docs/v2/instruments/) |
| ProductName | string | Product type of the order placed - [here](/docs/v2/annexure/#product-type) |
| Status | enum string | Last updated status of the order   `TRANSIT` `PENDING` `REJECTED` `CANCELLED` `TRADED` `EXPIRED` |
| LotSize | int | Lot Size in case of Derivatives |
| StrikePrice | float | Strike Price in which order is placed in Option contract |
| ExpiryDate | string | Expiry Date of the contract in which order is placed |
| OptType | string | `CE` or `PE` in case of Option contract |
| DisplayName | string | Name of instrument in which order is placed - Refer [here](/docs/v2/instruments/) |
| Isin | string | ISIN of the instrument in which order is placed |
| Series | string | Exchange series of the instrument |
| GoodTillDaysDate | string | Order validity in case of Forever Order |
| RefLtp | float | LTP at time of order update |
| TickSize | float | Tick size of the instrument |
| AlgoId | string | Exchange ID for special order types |
| Multiplier | int | In case of commodity and currency contracts |
| CorrelationId | string | The user/partner generated id for tracking back |
| Remarks | string | `Super Order` if the order is part of [super order](https://dhanhq.co/docs/v2/super-order) |

Note: For description of enum values, refer [Annexure](https://dhanhq.co/docs/v2/annexure)

---


# Source: https://dhanhq.co/docs/v2/market-quote/

# Market Quote

This API gives you snapshots of multiple instruments at once. You can fetch LTP, Quote or Market Depth of instruments via API which sends real time data at the time of API request.

|  |  |  |
| --- | --- | --- |
| POST | /marketfeed/ltp | Get ticker data of instruments |
| POST | /marketfeed/ohlc | Get OHLC data of instruments |
| POST | /marketfeed/quote | Get market depth data of instruments |

Info

You can fetch upto 1000 instruments in single API request with rate limit of 1 request per second.

## Ticker Data

Retrieve LTP for list of instruments with single API request

```python
    curl --request POST \
    --url https://api.dhan.co/v2/marketfeed/ltp \
    --header 'Accept: application/json' \
    --header 'Content-Type: application/json' \
    --header 'access-token: JWT' \
    --header 'client-id: 1000000001' \
    --data '{}'
```

**Header**

| Header | Description |
| --- | --- |
| access-token *required* | Access Token generated via Dhan |
| client-id *required* | User specific identification generated by Dhan |

**Request Structure**

```python
    {
    "NSE_EQ":[11536],
    "NSE_FNO":[49081,49082]
    }
```

**Parameters**

| Field | Field Type | Description |
| --- | --- | --- |
| [Exchange Segment ENUM](/docs/v2/annexure/#exchange-segment) *required* | array | Security ID - can be found [here](/docs/v2/instruments/) |

**Response Structure**

```python
{
    "data": {
        "NSE_EQ": {
            "11536": {
                "last_price": 4520
            }
        },
        "NSE_FNO": {
            "49081": {
                "last_price": 368.15
            },
            "49082": {
                "last_price": 694.35
            }
        }
    },
    "status": "success"
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| last\_price | float | LTP of the Instrument |

## OHLC Data

Retrieve the Open, High, Low and Close price along with LTP for specified list of instruments.

```python
    curl --request POST \
    --url https://api.dhan.co/v2/marketfeed/ohlc \
    --header 'Accept: application/json' \
    --header 'Content-Type: application/json' \
    --header 'access-token: JWT' \
    --header 'client-id: 1000000001' \
    --data '{}'
```

**Header**

| Header | Description |
| --- | --- |
| access-token *required* | Access Token generated via Dhan |
| client-id *required* | User specific identification generated by Dhan |

**Request Structure**

```python
    {
    "NSE_EQ":[11536],
    "NSE_FNO":[49081,49082]
    }
```

**Parameters**

| Field | Field Type | Description |
| --- | --- | --- |
| [Exchange Segment ENUM](/docs/v2/annexure/#exchange-segment) *required* | array | Security ID - can be found [here](/docs/v2/instruments/) |

**Response Structure**

```python
{
    "data": {
        "NSE_EQ": {
            "11536": {
                "last_price": 4525.55,
                "ohlc": {
                    "open": 4521.45,
                    "close": 4507.85,
                    "high": 4530,
                    "low": 4500
                }
            }
        },
        "NSE_FNO": {
            "49081": {
                "last_price": 368.15,
                "ohlc": {
                    "open": 0,
                    "close": 368.15,
                    "high": 0,
                    "low": 0
                }
            },
            "49082": {
                "last_price": 694.35,
                "ohlc": {
                    "open": 0,
                    "close": 694.35,
                    "high": 0,
                    "low": 0
                }
            }
        }
    },
    "status": "success"
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| last\_price | float | LTP of the Instrument |
| ohlc.open | float | Market opening price of the day |
| ohlc.close | float | Market closing price of the day |
| ohlc.high | float | Day High price |
| ohlc.low | float | Day Low price |

## Market Depth Data

Retrieve full details including market depth, OHLC data, Open Interest and Volume along with LTP for specified instruments.

```python
    curl --request POST \
    --url https://api.dhan.co/v2/marketfeed/quote \
    --header 'Accept: application/json' \
    --header 'Content-Type: application/json' \
    --header 'access-token: JWT' \
    --header 'client-id: 1000000001' \
    --data '{}'
```

**Header**

| Header | Description |
| --- | --- |
| access-token *required* | Access Token generated via Dhan |
| client-id *required* | User specific identification generated by Dhan |

**Request Structure**

```python
    {   
        "NSE_FNO":[49081]
    }
```

**Parameters**

cURL

| Field | Field Type | Description |
| --- | --- | --- |
| [Exchange Segment ENUM](/docs/v2/annexure/#exchange-segment) *required* | array | Security ID - can be found [here](/docs/v2/instruments/) |

**Response Structure**

```python
{
    "data": {
        "NSE_FNO": {
            "49081": {
                "average_price": 0,
                "buy_quantity": 1825,
                "depth": {
                    "buy": [
                        {
                            "quantity": 1800,
                            "orders": 1,
                            "price": 77
                        },
                        {
                            "quantity": 25,
                            "orders": 1,
                            "price": 50
                        },
                        {
                            "quantity": 0,
                            "orders": 0,
                            "price": 0
                        },
                        {
                            "quantity": 0,
                            "orders": 0,
                            "price": 0
                        },
                        {
                            "quantity": 0,
                            "orders": 0,
                            "price": 0
                        }
                    ],
                    "sell": [
                        {
                            "quantity": 0,
                            "orders": 0,
                            "price": 0
                        },
                        {
                            "quantity": 0,
                            "orders": 0,
                            "price": 0
                        },
                        {
                            "quantity": 0,
                            "orders": 0,
                            "price": 0
                        },
                        {
                            "quantity": 0,
                            "orders": 0,
                            "price": 0
                        },
                        {
                            "quantity": 0,
                            "orders": 0,
                            "price": 0
                        }
                    ]
                },
                "last_price": 368.15,
                "last_quantity": 0,
                "last_trade_time": "01/01/1980 00:00:00",
                "lower_circuit_limit": 48.25,
                "net_change": 0,
                "ohlc": {
                    "open": 0,
                    "close": 368.15,
                    "high": 0,
                    "low": 0
                },
                "oi": 0,
                "oi_day_high": 0,
                "oi_day_low": 0,
                "sell_quantity": 0,
                "upper_circuit_limit": 510.85,
                "volume": 0
            }
        }
    },
    "status": "success"
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| average\_price | float | Volume weighted average price of the day |
| buy\_quantity | int | Total buy order quantity pending at the exchange |
| sell\_quantity | int | Total sell order quantity pending at the exchange |
| depth.buy.quantity | int | Number of quantity at this price depth |
| depth.buy.orders | int | Number of open BUY orders at this price depth |
| depth.buy.price | float | Price at which the BUY depth stands |
| depth.sell.quantity | int | Number of quantity at this price depth |
| depth.sell.orders | int | Number of open SELL orders at this price depth |
| depth.sell.price | float | Price at which the SELL depth stands |
| last\_price | float | Last traded price |
| last\_quantity | int | Last traded quantity |
| last\_trade\_time | string | Last traded quantity |
| lower\_circuit\_limit | float | Current lower circuit limit |
| upper\_circuit\_limit | float | Current upper circuit limit |
| net\_change | float | Absolute change in LTP from previous day closing price |
| volume | int | Total traded volume for the day |
| oi | int | Open Interest in the contract (for Derivatives) |
| oi\_day\_high | int | Highest Open Interest for the day (only for NSE\_FNO) |
| oi\_day\_low | int | Lowest Open Interest for the day (only for NSE\_FNO) |
| ohlc.open | float | Market opening price of the day |
| ohlc.close | float | Market closing price of the day |
| ohlc.high | float | Day High price |
| ohlc.low | float | Day Low price |

Note: For description of enum values, refer [Annexure](https://dhanhq.co/docs/v2/annexure)

---


# Source: https://dhanhq.co/docs/v2/live-market-feed/

# Live Market Feed

Real-time Market Data across exchanges and segments can now be availed on your system via WebSocket. WebSocket provides an efficient means to receive live market data. WebSocket keeps a persistent connection open, allowing the server to push real-time data to your systems.

All Dhan platforms work on these same market feed WebSocket connections that deliver lightning fast market data to you. Do note that this is **tick-by-tick event based data** that is sent over the websocket.

> You can establish upto five WebSocket connections per user with 5000 instruments on each connection.

All request messages over WebSocket are in JSON whereas all response messages over WebSocket are in Binary. You will require WebSocket library in any programming language to be able to use Live Market Feed along with Binary converter.

Using DhanHQ Libraries for WebSockets

- You can use [DhanHQ Python Library](https://github.com/dhan-oss/DhanHQ-py) to quick start with Live Market Feed.

## Establishing Connection

To establish connection with DhanHQ WebSocket for Market Feed, you can to the below endpoint using WebSocket library.

```python
wss://api-feed.dhan.co?version=2&token=eyxxxxx&clientId=100xxxxxxx&authType=2
```

**Query Parameters**

| Field | Description |
| --- | --- |
| version *required* | `2` for DhanHQ v2 |
| token *required* | Access Token generated via Dhan |
| clientId *required* | User specific identification generated by Dhan |
| authType *required* | `2` by Default |




### Adding Instruments

You can subscribe upto 5000 instruments in a single connection and receive market data packets. For subscribing, this can be done using JSON message which needs to be send over WebSocket connection.

Note

You can only send upto 100 instruments in a single JSON message. You can send multiple messages over a single connection to subscribe to all instruments and receive data.

**Request Structure**

```python
{
    "RequestCode" : 15,
    "InstrumentCount" : 2,
    "InstrumentList" : [
        {
            "ExchangeSegment" : "NSE_EQ",
            "SecurityId" : "1333"
        },
        {
            "ExchangeSegment" : "BSE_EQ",
            "SecurityId" : "532540"
        }
    ]
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| RequestCode *required* | int | Code for subscribing to particular data mode.  Refer to [feed request code](/docs/v2/annexure/#feed-request-code) to subscribe to required data mode |
| InstrumentCount *required* | int | No. of instruments to subscribe from this request |
| InstrumentList.ExchangeSegment *required* | enum string | Exchange Segment of instrument to be subscribed as found in [Annexure](/docs/v2/annexure/#exchange-segment) |
| InstrumentList.SecurityId *required* | string | Exchange standard ID for each scrip. Refer [here](/docs/v2/instruments/) |

### Keeping Connection Alive

To keep the WebSocket connection alive and prevent it from closing, the server side uses **Ping-Pong** module. Server side sends ping every 10 seconds to the client server (in this case, your system) to maintain WebSocket status as open.

An automated pong is sent by websocket library. You can use the same as response to the ping.

> In case the client server does not respond for more than 40 seconds, the connection is closed from server side and you will have to reestablish connection.

## Market Data

The market feed data is sent as structured binary packet which is shared at super fast speed.

DhanHQ Live Market Feed is real-time data and there are three modes in which you can receive the data, depending on your use case:

* [Ticker Data](#ticker-packet)
* [Quote Data](#quote-packet)
* [Full Data](#full-packet)

![Subscribing Instruments](../img/WS02.png)

### Binary Response

Binary messages consist of sequences of bytes that represent the data. This contrasts with text messages, which use character encoding (e.g., UTF-8) to represent data in a readable format. Binary messages require parsing to extract the relevant information.

The reason for us to choose binary messages over text or JSON is to have compactness, speed and flexibility on data to be shared at lightning fast speed.

All responses from Dhan Market Feed consists of [Response Header](#response-header) and Payload. Header for every response message remains the same with different [feed response code](/docs/v2/annexure/#feed-response-code), while the payload can be different.

**Endianness**  
Endianness determines the order in which bytes are arranged for multi-byte data (like integers and floats).

**Types:**  
- **Little Endian**: Least significant byte first (0x78, 0x56, 0x34, 0x12)  
- **Big Endian**: Most significant byte first (0x12, 0x34, 0x56, 0x78)

The data on DhanHQ Websockets are sent in Little Endian. In case your system is Big Endian, you will have to define endianness while reading the websocket.

### Response Header

The response header message is of 8 bytes which will remain same as part of all the response messages. The message structure is given as below.

| Bytes | Type | Size | Description |
| --- | --- | --- | --- |
| `1` | [ ] byte | `1` | Feed Response Code can be referred in [Annexure](/docs/v2/annexure/#feed-response-code) |
| `2-3` | int16 | `2` | Message Length of the entire payload packet |
| `4` | [ ] byte | `1` | Exchange Segment can be referred in [Annexure](/docs/v2/annexure/#exchange-segment) |
| `5-8` | int32 | `4` | Security ID - can be found [here](/docs/v2/instruments/) |

### Ticker Packet

This packet consists of Last Traded Price (LTP) and Last Traded Time (LTT) data across segments.

| Bytes | Type | Size | Description |
| --- | --- | --- | --- |
| `0-8` | [ ] array | `8` | [Response Header](#response-header) with code `2`  Refer to [enum](/docs/v2/annexure/#feed-response-code) for values |
| `9-12` | float32 | `4` | Last Traded Price of the subscribed instrument |
| `13-16` | int32 | `4` | Last Trade Time (EPOCH) |

#### Prev Close

Whenever any instrument is subscribed for any data packet, we also send this packet which has Previous Day data to make it easier for day on day comparison.

| Bytes | Type | Size | Description |
| --- | --- | --- | --- |
| `0-8` | [ ] array | `8` | [Response Header](##response-header) with code `6`  Refer to [enum](/docs/v2/annexure/#feed-response-code) for values |
| `9-12` | float32 | `4` | Previous day closing price |
| `13-16` | int32 | `4` | Open Interest - previous day |

### Quote Packet

This data packet is for all instruments across segments and exchanges which consists of complete trade data, along with Last Trade Price (LTP) and other information like update time and quantity.

| Bytes | Type | Size | Description |
| --- | --- | --- | --- |
| `0-8` | [ ] array | `8` | [Response Header](#response-header) with code `4`  Refer to [enum](/docs/v2/annexure/#feed-response-code) for values |
| `9-12` | float32 | `4` | Latest Traded Price of the subscribed instrument |
| `13-14` | int16 | `2` | Last Traded Quantity |
| `15-18` | int32 | `4` | Last Trade Time (LTT) - EPOCH |
| `19-22` | float32 | `4` | Average Trade Price (ATP) |
| `23-26` | int32 | `4` | Volume |
| `27-30` | int32 | `4` | Total Sell Quantity |
| `31-34` | int32 | `4` | Total Buy Quantity |
| `35-38` | float32 | `4` | Day Open Value |
| `39-42` | float32 | `4` | Day Close Value - only sent post market close |
| `43-46` | float32 | `4` | Day High Value |
| `47-50` | float32 | `4` | Day Low Value |

#### OI Data

Whenever you subscribe to Quote Data, you also receive Open Interest (OI) data packets which is important for Derivative Contracts.

| Bytes | Type | Size | Description |
| --- | --- | --- | --- |
| `0-8` | [ ] array | `8` | [Response Header](#response-header) with code `5`  Refer to [enum](/docs/v2/annexure/#feed-response-code) for values |
| `9-12` | int32 | `4` | Open Interest of the contract |



### Full Packet

This data packet is for all instruments across segments and exchanges which consists of complete trade data along with Market Depth and OI data in a single packet.

| Bytes | Type | Size | Description |
| --- | --- | --- | --- |
| `0-8` | [ ] array | `8` | [Response Header](#response-header) with code `8`  Refer to [enum](/docs/v2/annexure/#feed-response-code) for values |
| `9-12` | float32 | `4` | Latest Traded Price of the subscribed instrument |
| `13-14` | int16 | `2` | Last Traded Quantity |
| `15-18` | int32 | `4` | Last Trade Time (LTT) - EPOCH |
| `19-22` | float32 | `4` | Average Trade Price (ATP) |
| `23-26` | int32 | `4` | Volume |
| `27-30` | int32 | `4` | Total Sell Quantity |
| `31-34` | int32 | `4` | Total Buy Quantity |
| `35-38` | int32 | `4` | Open Interest in the contract (for Derivatives) |
| `39-42` | int32 | `4` | Highest Open Interest for the da (only for NSE\_FNO) |
| `43-46` | int32 | `4` | Lowest Open Interest for the day (only for NSE\_FNO) |
| `47-50` | float32 | `4` | Day Open Value |
| `51-54` | float32 | `4` | Day Close Value - only sent post market close |
| `55-58` | float32 | `4` | Day High Value |
| `59-62` | float32 | `4` | Day Low Value |
| `63-162` | Market Depth Structure | `100` | 5 packets of 20 bytes each for each instrument in below provided structure |

Each of these 5 packets will be received in the following packet structure:

| Bytes | Type | Size | Description |
| --- | --- | --- | --- |
| `1-4` | int32 | `4` | Bid Quantity |
| `5-8` | int32 | `4` | Ask Quantity |
| `9-10` | int16 | `2` | No. of Bid Orders |
| `11-12` | int16 | `2` | No. of Ask Orders |
| `13-16` | float32 | `4` | Bid Price |
| `17-20` | float32 | `4` | Ask Price |

## Feed Disconnect

If you want to disconnect WebSocket, you can send below JSON request message via the connection.

```python
{
    "RequestCode" : 12
}
```

In case of WebSocket disconnection from server side, you will receive disconnection packet, which will have disconnection reason code.

* If more than 5 websockets are established, then the first socket will be disconnected with `805` with every additional connection.

| Bytes | Type | Size | Description |
| --- | --- | --- | --- |
| `0-8` | [ ] array | `8` | [Response Header](#request-header) with code `50`  Refer to [enum](/docs/v2/annexure/#feed-response-code) for values |
| `9-10` | int16 | `2` | Disconnection message code - [here](/docs/v2/annexure/#data-api-error) |

You can find detailed Disconnection message code description [here](/docs/v2/annexure/#data-api-error).

---


# Source: https://dhanhq.co/docs/v2/historical-data/

# Historical Data

This API gives you historical candle data for the desired scrip across segments & exchange. This data is presented in the form of a candle and gives you timestamp, open, high, low, close & volume.

|  |  |  |
| --- | --- | --- |
| POST | /charts/historical | Get OHLC for daily timeframe |
| POST | /charts/intraday | Get OHLC for minute timeframe |

## Daily Historical Data

Retrieve OHLC & Volume of daily candle for desired instrument. The data for any scrip is available back upto the date of its inception.

```python
curl --request POST \
--url https://api.dhan.co/v2/charts/historical \
--header 'Content-Type: application/json' \
--header 'access-token: JWT' \
--data '{}'
```

**Request Structure**

```python
    {
        "securityId": "1333",
        "exchangeSegment":"NSE_EQ",
        "instrument": "EQUITY",
        "expiryCode": 0,
        "oi": false,
        "fromDate": "2022-01-08",
        "toDate": "2022-02-08"
    }
```

**Parameters**

| Field | Field Type | Description |
| --- | --- | --- |
| securityId *required* | string | Exchange standard ID for each scrip. Refer [here](/docs/v2/instruments/) |
| exchangeSegment *required* | enum string | Exchange & segment for which data is to be fetched - [here](/docs/v2/annexure/#exchange-segment) |
| instrument  *required* | enum string | Instrument type of the scrip . Refer [here](/docs/v2/annexure/#instrument) |
| expiryCode   *optional* | enum integer | Expiry of the instruments in case of derivatives. Refer [here](/docs/v2/instruments/) |
| oi  *optional* | boolean | Open Interest data for Futures & Options |
| fromDate  *required* | string | Start date of the desired range |
| toDate  *required* | string | End date of the desired range (non-inclusive) |

**Response Structure**

```python
{
    "open": [
            3978,3856,3925,3918,3877.85,3992.7,4033.95,4012,3910,3807,3840,3769.5,3731,3646,3749,
            3770,3827.9,3851,3815.3,3791
        ],
    "high": [
        3978,3925,3929,3923,3977,4043,4041.7,4012,3920,3851.55,3849.65,3809.4,3733.4,3729.8,
        3758,3808,3864,3882.5,3824.7,3831.8
        ],
    "low":  [
        3861,3856,3836.55,3857,3860.05,3962.3,3980,3910.5,3811,3771.1,3740.1,3722.2,3625.1,
        3646,3721.4,3736.4,3800.65,3816.05,3769,3756.15
        ],
    "close": [
        3879.85,3915.9,3859.9,3897.9,3968.15,4019.15,3990.6,3914.65,3826.55,3833.5,3771.35,
        3769.9,3649.25,3690.05,3736.25,3800.65,3856.2,3824.6,3814.9,3779
        ],
    "volume":[
        3937092,1906106,3203744,6684507,3348123,3442604,2389041,3102539,6176776,3112358,     
        3258414,3330501,5718297,3143862,2739393,2105169,1984212,1960538,2307366,1919149
        ],
    "timestamp": [
        1326220200,1326306600,1326393000,1326479400,1326565800,1326825000,1326911400,
        1326997800,1327084200,1327170600,1327429800,1327516200,1327689000,1327775400,
        1328034600,1328121000,1328207400,1328293800,1328380200,1328639400
        ],
    "open_interest": [
        0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
}
```

**Parameters**

| Field | Field Type | Description |
| --- | --- | --- |
| open | float | Open price of the timeframe |
| high | float | High price in the timeframe |
| low | float | Low price in the timeframe |
| close | float | Close price of the timeframe |
| volume | int | Volume traded in the timeframe |
| timestamp | int | Epoch timestamp |

## Intraday Historical Data

Retrieve Open, High, Low, Close, OI & Volume of 1, 5, 15, 25 and 60 min candle for desired instrument for last 5 years. This data available for all exchanges and segments for all active instruments.

```python
    curl --request POST \
    --url https://api.dhan.co/v2/charts/intraday \
    --header 'Accept: application/json' \
    --header 'Content-Type: application/json' \
    --header 'access-token: ' \
    --data '{}'
```

**Request Structure**

```python
{
"securityId": "1333",
"exchangeSegment": "NSE_EQ",
"instrument": "EQUITY",
"interval": "1",
"oi": false,
"fromDate": "2024-09-11 09:30:00",
"toDate": "2024-09-15 13:00:00"
}
```

**Parameters**

| Field | Field Type | Description |
| --- | --- | --- |
| securityId *required* | string | Exchange standard ID for each scrip. Refer [here](/docs/v2/instruments/) |
| exchangeSegment *required* | enum string | Exchange & segment for which data is to be fetched - [here](/docs/v2/annexure/#exchange-segment) |
| instrument  *required* | enum string | Instrument type of the scrip . Refer [here](/docs/v2/annexure/#instrument) |
| interval   *required* | enum integer | Minute intervals in timeframe   `1`, `5`, `15`, `25`, `60` |
| oi  *optional* | boolean | Open Interest data for Futures & Options |
| fromDate  *required* | string | Start date of the desired range |
| toDate  *required* | string | End date of the desired range |

Note

The data size is very large in this scenario and only 90 days of data can be polled at once for any of the above time intervals. It is recommended that you store this data at your end for day-to-day analysis.

**Response Structure**

```python
{
    "open":   [
    3750,3757.85,3751.2,3763.6,3759.55,3759,3761,3763,3767.25,3773.65,3766.1,3765.65,3767.1,3774.15,3775.9,3774.95,3773.2,3774.7,3772.25,3774.85,3767.2,3768,3768.95,3768.85,3769.3,3773.55,3773.95,3770,3770.25,3769.1,3765.3,3760.2,3762.45,3765.4,
    3767.8,3768.8,3764.75,3763.2,3764.9,3764.9,3765.45,3764,3765,3764.5,3764.3,3764.85,3765,3762,3764.2,3762.05,3757.55,3757,3754.25,3755.95,3760.75,3760.05,3757.45,3760.2,3757.1,3758.1,3757.6,3758.8,3760.35,3761.05,3761.15,3760.4,3760.25,3760.85,
    3758.6,3760,3760.6,3759.05,3757.55,3758.2,3759.6,3760,3759,3759.3,3759.9,3758.8,3758.6,3759.5,3759.55,3757.4,3756.9,3757,3756.4,3757.6,3757.6,3757.05,3756.4,3757.95,3756.45,3757.4,3759.95
    ],
    "high":   [
    3750,3757.9,3763.6,3765.2,3763.15,3768,3764.75,3766.9,3775,3773.8,3766.9,3768.5,3777.7,3777,3777.95,3775.4,3775.95,3775,3775,3774.95,3770.8,3770,3769,3769.85,3773.6,3776,3774.8,3772.15,3773.55,3772.1,3765.3,3763.85,3768.95,3769,3769.85,3769,3766.55,
    3765.8,3765.4,3766,3766,3765.4,3767.35,3765,3765,3767.15,3765.5,3764.25,3764.2,3762.05,3760,3757.1,3757.3,3761.95,3762,3761,3759.95,3760.2,3758.15,3759.4,3759,3761.5,3762.6,3762.1,3762.75,3761.65,3761.55,3762,3760,3762,3763.7,3762.85,3762.8,3762,3761.85,3764.95,
    3765,3763.55,3764,3765,3763.35,3761.6,3764,3763.4,3762.8,3763.5,3763.8,3763,3760,3762.55,3761,3761,3761.15,3760.9,3763.4,3761.4,3761.4,3762,3762,3762,3761.95,3762,3762,3758.5,3758.65,3761.45,3760.95,3759.85,3758.55,3757.85,3756.5,3755.9,3756.3,3755.75,3757.4,
    3759.6,3758.8,3758.9,3758.25,3758.2,3758.6,3760,3761.55,3760.6,3759.05,3758.4,3759.6,3760.9,3760.25,3763.55,3761,3760.95,3760,3759.65,3759.55,3759.55,3758.7,3757.05,3757.35,3756.95,3758.25,3758,3758.8,3758.4,3759.85,3758.9,3759.35,3759.95
    ],
    "low":      [
        3750,3746.1,3749.25,3757,3758.65,3758.6,3758,3761,3767.25,3764,3762.15,3765.15,3767.1,3772.25,3772.55,3772.35,3773.2,3772,3771.6,3767.3,3767,3767.4,3766.1,3767.55,3769.3,3773,3770,3768.85,
        3769,3765,3760,3760,3762.45,3765.25,3765,3761.15,3763.2,3762.4,3764.3,3764,3764,3763.5,3764.25,3762.65,3763.55,3764.15,3762,3761.05,3761.5,3756.7,3756.65,3752.75,3753,3755.5,3758.15,3757.55,
        3755.3,3756,3756.55,3757.05,3757.15,3757.6,3760,3760,3760,3760,3759.55,3759.5,3758.05,3759.5,3761.05,3760.3,3760.05,3760.1,3759,3761.1,3762.85,3761.2,3759.55,3761.05,3760.95,3760,3760,
        3761.85,3761.55,3761.4,3761.95,3759.1,3758.05,3758.55,3759.9,3758.35,3760,3759.8,3759.5,3760,3759.75,3759.65,3760,3760.15,3760.1,3760,3756.5,3757.9,3758.45,3758.8,3759,3758,3757,3753.6,
        3754,3755.1,3755.05,3755.05,3755.6,3756.4,3757.5,3756.25,3756,3756.05,3756.1,3756.7,3759.45,3758.3,3757.15,3756.85,3757.05,3759,3758.4,3759,3758,3758.65,3758,3758.5,3758.55,3758,3756.5,3756.15,3756,3755.35,3755.9,3756.05,3756,3756,3756.2,3756.45,3756.7,3756.9
    ],
    "close":    [
        3750,3751.25,3763.6,3760.85,3759,3761.3,3762.95,3766.9,3772.95,3766.35,3765.55,3767.3,3774.1,3774.95,3775,3773,3775,3772.15,3774.95,3767.95,3768.5,3769,3768.55,3769.85,3773.15,3774,3770,
        3771.35,3769.4,3765,3760.35,3762.5,3765.95,3768.35,3767.3,3764.05,3763.2,3764.95,3764.95,3765.45,3764,3764.9,3764.6,3764.3,3764.95,3765,3762,3764.2,3762.1,3758,3757.1,3753.85,3755.95,3760.65,
        3760.35,3757.55,3759.95,3757.1,3757.5,3757.65,3758.8,3761.5,3761.05,3761.15,3761.1,3760.25,3759.55,3760,3759.5,3761.1,3761.55,3761,3761,3760.2,3761.6,3763.35,3762.85,3761.55,3762.6,3763.35,3761,
        3761.05,3763.65,3762.8,3761.55,3763.5,3762.35,3759.95,3759,3760.5,3760.3,3761,3760.9,3759.9,3761.3,3761.3,3760,3760.7,3760.05,3760.9,3761.95,3762,3758.35,3758.45,3758.45,3760.9,3759.9,3758.55,3757,
        3754.9,3755.7,3755.1,3755.55,3755.75,3756.6,3758.85,3758.7,3756.25,3757.4,3757.65,3758.6,3760,3760.6,3759.05,3757.55,3756.85,3759.2,3759.5,3759,3759.65,3759.9,3758.8,3759.65,3759.5,3759.55,3758.85,3756.9,3756.9,3756.4,3756.6,3756.2,3757.5,3756.4,3757.9,3756.3,3757.35,3758.75,3756.9
    ],
    "volume":   [
        166,53629,34592,20802,11262,17549,13239,11514,20125,12948,11761,8039,21998,9373,13171,9564,7287,6217,13260,5135,9676,5218,7365,3541,5547,13108,3659,4587,6499,12101,12766,12216,7619,8063,9830,6717,5976,
        3907,3907,7276,6048,3581,6525,3270,2139,6391,3418,3290,3636,9730,3460,8773,4929,7772,6410,5050,3300,5275,1871,1951,1901,2265,3353,2221,2822,2668,2840,3109,1995,3522,6635,2914,2056,2781,3331,3383,3125,2235,6889,
        3398,1671,2054,2856,1668,1431,2576,1791,4715,1751,4474,1973,2292,2325,1845,2906,2240,2032,2984,2262,2980,2796,3117,7508,1971,2004,3972,2181,2511,2316,5713,2506,1717,1967,2072,2304,2248,1861,1503,2358,1845,2329,
        2407,2589,1542,1571,1707,2355,2696,3459,4160,2037,2036,1972,1491,1664,1846,2049,2149,3937,2603,1765,2005,2867,2141,2103,2279,2490,2111
    ],
    "timestamp":[
        1328845020,1328845500,1328845560,1328845620,1328845680,1328845740,1328845800,1328845860,1328845920,1328845980,1328846040,1328846100,1328846160,1328846220,1328846280,1328846340,1328846400,1328846460,1328846520,1328846580,1328846640,1328846700,1328846760,1328846820,1328846880,1328846940,1328847000,1328847060,1328847120,1328847180,1328847240,1328847300,1328847360,1328847420,1328847480,1328847540,
        1328847600,1328847660,1328847720,1328847780,1328847840,1328847900,1328847960,1328848020,1328848080,1328848140,1328848200,1328848260,1328848320,1328848380,1328848440,1328848500,1328848560,1328848620,1328848680,1328848740,1328848800,1328848860,1328848920,1328848980,1328849040,1328849100,1328849160,1328849220,1328849280,1328849340,1328849400,1328849460,1328849520,1328849580,1328849640,1328849700,
        1328849760,1328849820,1328849880,1328849940,1328850000,1328850060,1328850120,1328850180,1328850240,1328850300,1328850360,1328850420,1328850480,1328850540,1328850600,1328850660,1328850720,1328850780,1328850840,1328850900,1328850960,1328851020,1328851080,1328851140,1328851200,1328851260,1328851320,1328851380,1328851440,1328851500,1328851560,1328851620,1328851680,1328851740,1328851800,1328851860,
        1328851920,1328851980,1328852040,1328852100,1328852160,1328852220,1328852280,1328852340,1328852400,1328852460,1328852520,1328852580,1328852640,1328852700,1328852760,1328852820,1328852880,1328852940,1328853000,1328853060,1328853120,1328853180,1328853240,1328853300,1328853360,1328853420,1328853480,1328853540,1328853600,1328853660,1328853720,1328853780,1328853840,1328853900,1328853960,1328854020,1328854080,1328854140,1328854200,1328854260
    ],
    "open_interest":[
        0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
    ]
}
```

**Parameters**

| Field | Field Type | Description |
| --- | --- | --- |
| open | float | Open price of the timeframe |
| high | float | High price in the timeframe |
| low | float | Low price in the timeframe |
| close | float | Close price of the timeframe |
| volume | int | Volume traded in the timeframe |
| timestamp | int | Epoch timestamp |

Note: For description of enum values, refer [Annexure](https://dhanhq.co/docs/v2/annexure)

---


# Source: https://dhanhq.co/docs/v2/option-chain/

# Option Chain

This API gives entire Option Chain of any Option Instrument, across exchanges and segments - for NSE, BSE and MCX traded options. With Option Chain, you get OI, greeks, volume, top bid/ask and price data of all strikes of a particular underlying.

|  |  |  |
| --- | --- | --- |
| POST | /optionchain | Get Option Chain of any instrument |
| POST | /optionchain/expirylist | Expiry List for Options of Underlying |

Info

You can call Option Chain API once every 3 seconds. This will give you latest updated data.

## Option Chain

Retrieve real-time Option Chain across exchanges for all underlying. You can fetch Open Interest (OI), Greeks, Volume, Last Traded Price, Best Bid/Ask and Implied Volatility (IV) across all strikes for any underlying.

```python
    curl --location 'https://api.dhan.co/v2/optionchain' \
    --header 'access-token: JWT' \
    --header 'client-id: ClientId' \
    --header 'Content-Type: application/json' \
    --data '{}'
```

**Header**

| Header | Description |
| --- | --- |
| access-token *required* | Access Token generated via Dhan |
| client-id *required* | User specific identification generated by Dhan |

**Request Structure**

```python
    {
    "UnderlyingScrip":13,
    "UnderlyingSeg":"IDX_I",
    "Expiry":"2024-10-31"
    }
```

**Parameters**

| Field | Field Type | Description |
| --- | --- | --- |
| UnderlyingScri *required* | int | Security ID of Underlying Instrument - can be found [here](/docs/v2/instruments/) |
| UnderlyingSeg | enum string | Exchange & segment of underlying for which data is to be fetched - [here](/docs/v2/annexure/#exchange-segment) |
| Expiry | string | Expiry Date of Option, for which Option Chain is requested. List of active expiries can be fetched from [here](/docs/v2/option-chain/#expiry-list) |

**Response Structure**

```python
{
    "data": {
        "last_price": 24964.25,
        "oc": {
            .
            .
            "25000.000000": {
                "ce": {
                    "greeks": {
                        "delta": 0.52546,
                        "theta": -12.88756,
                        "gamma": 0.00136,
                        "vega": 12.98931
                    },
                    "implied_volatility": 8.945204889199001,
                    "last_price": 125.05,
                    "oi": 5962675,
                    "previous_close_price": 190.45,
                    "previous_oi": 3939375,
                    "previous_volume": 831463,
                    "top_ask_price": 124.9,
                    "top_ask_quantity": 1000,
                    "top_bid_price": 124,
                    "top_bid_quantity": 100,
                    "volume": 84202625
                },
                "pe": {
                    "greeks": {
                        "delta": -0.48099,
                        "theta": -10.56587,
                        "gamma": 0.00092,
                        "vega": 13.00105
                    },
                    "implied_volatility": 13.321804909313869,
                    "last_price": 165,
                    "oi": 5059700,
                    "previous_close_price": 153.6,
                    "previous_oi": 4667700,
                    "previous_volume": 1047989,
                    "top_ask_price": 165,
                    "top_ask_quantity": 375,
                    "top_bid_price": 164.05,
                    "top_bid_quantity": 50,
                    "volume": 81097175
                }
            }
            .
            .
            .
        }
    }
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| data.last\_price | float | LTP of the Underlying |
| data.oc | array | Option Chain Array - Strike Wise |
| data.oc.{strike} | array | Strike Price for Underlying |
| data.oc.{strike}.ce | array | Call Option data of particular strike |
| data.oc.{strike}.pe | array | Put Option data of particular strike |

**Call/Put Option Data**

| Field | Type | Description |
| --- | --- | --- |
| greeks.delta | float | Measures the change of option's premium based on every 1 rupee change in underlying |
| greeks.theta | float | Measures measures how quickly an option's value decreases over time |
| greeks.gamma | float | Rate of change in an option's delta in relation to the price of the underlying asset |
| greeks.vega | float | Measures the change of option's premium in response to a 1% change in implied volatility |
| implied\_volatility | float | Value of expected volatility of a stock over the life of the option |
| last\_price | float | Last Traded Price of the Option Instrument |
| oi | int | Open Interest of the Option Instrument |
| previous\_close\_price | float | Previous day close price |
| previous\_oi | int | Previous day Open Interest |
| previous\_volume | int | Previous day volume |
| top\_ask\_price | float | Current best ask price available |
| top\_ask\_quantity | int | Quantity available at current best ask price |
| top\_bid\_price | float | Current best bid price available |
| top\_bid\_quantity | int | Quantity available at current best bid price |
| volume | int | Day volume for Option Instrument |

## Expiry List

Retrieve dates of all expiries of any underlying, for which Options Instruments are active.

```python
    curl --request POST \
    --url https://api.dhan.co/v2/optionchain/expirylist \
    --header 'Content-Type: application/json' \
    --header 'access-token: JWT' \
    --header 'client-id: 1000000001' \
    --data '{}'
```

**Header**

| Header | Description |
| --- | --- |
| access-token *required* | Access Token generated via Dhan |
| client-id *required* | User specific identification generated by Dhan |

**Request Structure**

```python
    {
    "UnderlyingScrip":13,
    "UnderlyingSeg":"IDX_I"
    }
```

**Parameters**

| Field | Field Type | Description |
| --- | --- | --- |
| UnderlyingScri *required* | int | Security ID of Underlying Instrument - can be found [here](/docs/v2/instruments/) |
| UnderlyingSeg | enum string | Exchange & segment of underlying for which data is to be fetched - [here](/docs/v2/annexure/#exchange-segment) |

**Response Structure**

```python
{
    "data": [
        "2024-10-17",
        "2024-10-24",
        "2024-10-31",
        "2024-11-07",
        "2024-11-14",
        "2024-11-28",
        "2024-12-26",
        "2025-03-27",
        "2025-06-26",
        "2025-09-25",
        "2025-12-24",
        "2026-06-25",
        "2026-12-31",
        "2027-06-24",
        "2027-12-30",
        "2028-06-29",
        "2028-12-28",
        "2029-06-28"
    ],
    "status": "success"
}
```

**Parameters**

| Field | Type | Description |
| --- | --- | --- |
| data[] | array | All expiry dates of underlying in `YYYY-MM-DD` |

Note

The rate limit applicable for Option Chain API is at 1 request per 3 second. This is because OI data gets updated slow, compared to LTP or other data parameter.

Note: For description of enum values, refer [Annexure](https://dhanhq.co/docs/v2/annexure)

---


# Source: https://dhanhq.co/docs/v2/annexure/

# Annexure

## Exchange Segment

| Attribute | Exchange | Segment | enum |
| --- | --- | --- | --- |
| IDX\_I | Index | Index Value | `0` |
| NSE\_EQ | NSE | Equity Cash | `1` |
| NSE\_FNO | NSE | Futures & Options | `2` |
| NSE\_CURRENCY | NSE | Currency | `3` |
| BSE\_EQ | BSE | Equity Cash | `4` |
| MCX\_COMM | MCX | Commodity | `5` |
| BSE\_CURRENCY | BSE | Currency | `7` |
| BSE\_FNO | BSE | Futures & Options | `8` |

## Product Type

CO & BO product types will be valid only for Intraday.

| Attribute | Detail |
| --- | --- |
| CNC | Cash & Carry for equity deliveries |
| INTRADAY | Intraday for Equity, Futures & Options |
| MARGIN | Carry Forward in Futures & Options |
| CO | Cover Order |
| BO | Bracket Order |

## Order Status

| Attribute | Detail |
| --- | --- |
| TRANSIT | Did not reach the exchange server |
| PENDING | Awaiting execution |
| CLOSED | Used for Super Order, once both the entry and exit orders are placed |
| TRIGGERED | Used for Super Order, if Target or Stop Loss leg is triggered |
| REJECTED | Rejected by broker/exchange |
| CANCELLED | Cancelled by user |
| PART\_TRADED | Partial Quantity traded successfully |
| TRADED | Executed successfully |

## After Market Order time

| Attribute | Detail |
| --- | --- |
| PRE\_OPEN | AMO pumped at pre-market session |
| OPEN | AMO pumped at market open |
| OPEN\_30 | AMO pumped 30 minutes after market open |
| OPEN\_60 | AMO pumped 60 minutes after market open |

## Expiry Code

| Attribute | Detail |
| --- | --- |
| 0 | Current Expiry/Near Expiry |
| 1 | Next Expiry |
| 2 | Far Expiry |

## Instrument

| Attribute | Detail |
| --- | --- |
| INDEX | Index |
| FUTIDX | Futures of Index |
| OPTIDX | Options of Index |
| EQUITY | Equity |
| FUTSTK | Futures of Stock |
| OPTSTK | Options of Stock |
| FUTCOM | Futures of Commodity |
| OPTFUT | Options of Commodity Futures |
| FUTCUR | Futures of Currency |
| OPTCUR | Options of Currency |

## Feed Request Code

| Attribute | Detail |
| --- | --- |
| `11` | Connect Feed |
| `12` | Disconnect Feed |
| `15` | Subscribe - Ticker Packet |
| `16` | Unsubscribe - Ticker Packet |
| `17` | Subscribe - Quote Packet |
| `18` | Unsubscribe - Quote Packet |
| `21` | Subscribe - Full Packet |
| `22` | Unsubscribe - Full Packet |
| `23` | Subscribe - Full Market Depth |
| `24` | Unsubscribe - Full Market Depth |

## Feed Response Code

| Attribute | Detail |
| --- | --- |
| `1` | Index Packet |
| `2` | Ticker Packet |
| `4` | Quote Packet |
| `5` | OI Packet |
| `6` | Prev Close Packet |
| `7` | Market Status Packet |
| `8` | Full Packet |
| `50` | Feed Disconnect |

## Trading API Error

| Type | Code | Message |
| --- | --- | --- |
| Invalid Authentication | `DH-901` | Client ID or user generated access token is invalid or expired. |
| Invalid Access | `DH-902` | User has not subscribed to Data APIs or does not have access to Trading APIs. Kindly subscribe to Data APIs to be able to fetch Data. |
| User Account | `DH-903` | Errors related to User's Account. Check if the required segments are activated or other requirements are met. |
| Rate Limit | `DH-904` | Too many requests on server from single user breaching rate limits. Try throttling API calls. |
| Input Exception | `DH-905` | Missing required fields, bad values for parameters etc. |
| Order Error | `DH-906` | Incorrect request for order and cannot be processed. |
| Data Error | `DH-907` | System is unable to fetch data due to incorrect parameters or no data present. |
| Internal Server Error | `DH-908` | Server was not able to process API request. This will only occur rarely. |
| Network Error | `DH-909` | Network error where the API was unable to communicate with the backend system. |
| Others | `DH-910` | Error originating from other reasons. |

## Data API Error

| Code | Description |
| --- | --- |
| `800` | Internal Server Error |
| `804` | Requested number of instruments exceeds limit |
| `805` | Too many requests or connections. Further requests may result in the user being blocked. |
| `806` | Data APIs not subscribed |
| `807` | Access token is expired |
| `808` | Authentication Failed - Client ID or Access Token invalid |
| `809` | Access token is invalid |
| `810` | Client ID is invalid |
| `811` | Invalid Expiry Date |
| `812` | Invalid Date Format |
| `813` | Invalid SecurityId |
| `814` | Invalid Request |

---


# Source: https://dhanhq.co/docs/v2/instruments/

# Instrument List

You can fetch instrument list for all instruments which can be traded via Dhan by using below URL:

**Compact:**

```python
https://images.dhan.co/api-data/api-scrip-master.csv
```

**Detailed:**

```python
https://images.dhan.co/api-data/api-scrip-master-detailed.csv
```

This fetches list of instruments as CSV with Security ID and other important details which will help you build with DhanHQ APIs.

### Segmentwise List

You can fetch detailed instrument list for all instruments in a particular exchange and segment by passing the same in parameters as below:

```python
curl --location 'https://api.dhan.co/v2/instrument/{exchangeSegment}' \
```

> This helps to fetch instrument list of only one particular `exchangeSegment` at a time. The mapping of the same can be found [here](/docs/v2/annexure/#exchange-segment).

### Column Description

| Detailed `tag` | Compact `tag` | Description |
| --- | --- | --- |
| `EXCH_ID` | `SEM_EXM_EXCH_ID` | Exchange `NSE`  `BSE`  `MCX` |
| `SEGMENT` | `SEM_SEGMENT` | Segment  `C` - Currency  `D` - Derivatives  `E` - Equity  `M` - Commodity |
| `ISIN` | - | International Securities Identification Number(ISIN) - 12-digit alphanumeric code unique for instruments |
| `INSTRUMENT` | `SEM_INSTRUMENT_NAME` | Instrument defined by Exchange - defined [here](https://dhanhq.co/docs/v2/annexure/#instrument) |
| *removed* | `SEM_EXPIRY_CODE` | Expiry Code (applicable in case of Futures Contract) - defined [here](https://dhanhq.co/docs/v2/annexure/#expiry-code) |
| `UNDERLYING_SECURITY_ID` | - | Security ID of underlying instrument (applicable in case of derivative contracts) |
| `UNDERLYING_SYMBOL` | - | Symbol of underlying instrument (applicable in case of derivative contracts) |
| `SYMBOL_NAME` | `SM_SYMBOL_NAME` | Symbol name of instrument |
| *removed* | `SEM_TRADING_SYMBOL` | Exchange trading symbol of instrument |
| `DISPLAY_NAME` | `SEM_CUSTOM_SYMBOL` | Dhan display symbol name of instrument |
| `INSTRUMENT_TYPE` | `SEM_EXCH_INSTRUMENT_TYPE` | In addition to `INSTRUMENT` column, instrument type is defined by exchange adding more details about instrument |
| `SERIES` | `SEM_SERIES` | Exchange defined series for instrument |
| `LOT_SIZE` | `SEM_LOT_UNITS` | Lot Size in multiples of which instrument is traded |
| `SM_EXPIRY_DATE` | `SEM_EXPIRY_DATE` | Expiry date of instrument (applicable in case of derivative contracts) |
| `STRIKE_PRICE` | `SEM_STRIKE_PRICE` | Strike Price of Options Contract |
| `OPTION_TYPE` | `SEM_OPTION_TYPE` | Type of Options Contract  `CE` - Call  `PE` - Put |
| `TICK_SIZE` | `SEM_TICK_SIZE` | Minimum decimal point at which an instrument can be priced |
| `EXPIRY_FLAG` | `SEM_EXPIRY_FLAG` | Type of Expiry (applicable in case of option contracts)  `M` - Monthly Expiry  `W` - Weekly Expiry |
| `BRACKET_FLAG` | - | Bracket order status  `N` - Not available  `Y` - Allowed |
| `COVER_FLAG` | - | Cover order status  `N` - Not available  `Y` - Allowed |
| `ASM_GSM_FLAG` | - | Flag for instrument is ASM or GSM  `N` - Not in ASM/GSM  `R` - Removed from block  `Y` - ASM/GSM |
| `ASM_GSM_CATEGORY` | - | Category of instrument in ASM or GSM  `NA` in case of no surveillance |
| `BUY_SELL_INDICATOR` | - | Indicator to show if Buy and Sell is allowed in instrument  `A` if both Buy/Sell is allowed |
| `BUY_CO_MIN_MARGIN_PER` | - | Buy cover order minimum margin requirement (in percentage) |
| `SELL_CO_MIN_MARGIN_PER` | - | Sell cover order minimum margin requirement (in percentage) |
| `BUY_CO_SL_RANGE_MAX_PERC` | - | Buy cover order maximum range for stop loss leg (in percentage) |
| `SELL_CO_SL_RANGE_MAX_PERC` | - | Sell cover order maximum range for stop loss leg (in percentage) |
| `BUY_CO_SL_RANGE_MIN_PERC` | - | Buy cover order minimum range for stop loss leg (in percentage) |
| `SELL_CO_SL_RANGE_MIN_PERC` | - | Sell cover order minimum range for stop loss leg (in percentage) |
| `BUY_BO_MIN_MARGIN_PER` | - | Buy bracket order minimum margin requirement (in percentage) |
| `SELL_BO_MIN_MARGIN_PER` | - | Sell bracket order minimum margin requirement (in percentage) |
| `BUY_BO_SL_RANGE_MAX_PERC` | - | Buy bracket order maximum range for stop loss leg (in percentage) |
| `SELL_BO_SL_RANGE_MAX_PERC` | - | Sell bracket order maximum range for stop loss leg (in percentage) |
| `BUY_BO_SL_RANGE_MIN_PERC` | - | Buy bracket order minimum range for stop loss leg (in percentage) |
| `SELL_BO_SL_MIN_RANGE` | - | Sell bracket order minimum range for stop loss leg (in percentage) |
| `BUY_BO_PROFIT_RANGE_MAX_PERC` | - | Buy bracket order maximum range for target leg (in percentage) |
| `SELL_BO_PROFIT_RANGE_MAX_PERC` | - | Sell bracket order maximum range for target leg (in percentage) |
| `BUY_BO_PROFIT_RANGE_MIN_PERC` | - | Buy bracket order minimum range for target leg (in percentage) |
| `SELL_BO_PROFIT_RANGE_MIN_PERC` | - | Sell bracket order minimum range for target leg (in percentage) |
| `MTF_LEVERAGE` | - | MTF Leverage available (in x multiple) for eligible `EQUITY` instruments |

---
