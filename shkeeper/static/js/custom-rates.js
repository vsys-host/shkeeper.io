function changeSource(ind)
{
    let coinCostArray = document.getElementsByClassName("coin-cost");
    let ratesCurArray = document.getElementsByClassName("rates-current");

    let sourceType = selectArray[ind].value;
    if(sourceType == "manual")
    {
        coinCostArray[ind].style.display = "flex";
        ratesCurArray[ind].style.display = "none";
    }
    else if(sourceType == "binance"){
        coinCostArray[ind].style.display = "none";
        ratesCurArray[ind].style.display = "flex";
    }
}

function saveRates()
{
    let cryptos = document.querySelectorAll('.rates-name');
    cryptos.forEach( item => {
        let parent = item.parentNode;

        let crypto = parent.querySelector(".rates-name").getAttribute('crypto');
        let data = composeData(parent);

        sendSource(crypto, data);
    });

    function composeData(parentNode)
    {
        let fiat = parentNode.querySelector(".rates-name").getAttribute('fiat');
        let source = parentNode.querySelector(".rates-source-value").value;
        let rate = validateFloatValue(parentNode.querySelector(".rates-cost-value"));
        let fee = validateFloatValue(parentNode.querySelector(".rates-fee-value"));

        if(source == "manual")
        {
            return JSON.stringify({
                fiat: fiat,
                source: source,
                rate: rate,
                fee: fee
            });
        }
        else{
            return JSON.stringify({
                fiat: fiat,
                source: source,
                fee: fee
            });
        }


        function validateFloatValue(element)
        {
            element.value = parseFloat(element.value);
            if(element.value.match(/^\d+\.*\d*$/))
            {
            element.classList.remove("red-highlight");
            }
            else{
            element.classList.add("red-highlight");
            check = false;
            }
            return element.value;
        }
    }

    function sendSource(crypto,data)
    {
        const http = new XMLHttpRequest();
        http.open("POST"," /api/v1/" + crypto + "/exchange-rate",true);
        http.send(data);
        http.onload = function(){
            let data = checkAnswer(this);
            if(data!=false)
            {
                alert("Rates for " + crypto + " saved");
            }
            else{
                alert("Please input valid value for " + crypto);
            }
        }


        function checkAnswer(response)
        {
            if(response.status == 200)
            {
                let data = JSON.parse(response.responseText);
                if(data['status'] != "success")
                {
                    alert(data['message']);
                    return false;
                }
                else
                {
                    return data;
                }
            }
            alert("Response stauts: " + response.status);
            return false;
        }
    }


}

function refreshRates()
{
    let currentRates = document.getElementsByClassName("rates-current-value");
    for(let i = 0; i < currentRates.length; i++)
    {
        currentRates[i].id = currentRates[i].id.toLowerCase();
    }
    helperCycleBinanceRates(currentRates);
}

function helperCycleBinanceRates(currentRates)
{
    for(let i = 0; i < currentRates.length; i++)
    {
        getBinanceRealTRates(currentRates[i].id, currentRates[i]);
    }
}

function getBinanceRealTRates(pairName, currentRate)
{
    if (['usdtusdt', 'eth-usdtusdt', 'bnb-usdtusdt', 'polygon-usdtusdt', 'avalanche-usdtusdt'].includes(pairName)) {
        currentRate.innerHTML = "1";
        return;
    }

    if (['eth-usdcusdt', 'bnb-usdcusdt', 'polygon-usdcusdt', 'avalanche-usdcusdt'].includes(pairName)) {
        pairName = 'usdcusdt';
    }

    let url = 'wss://stream.binance.com:9443/ws/' + pairName + '@miniTicker';
    let bSocket = new WebSocket(url);
    bSocket.onmessage = function(data) {
        let quotation = JSON.parse(data.data);
        let price = parseFloat(quotation['c']);
        currentRate.innerHTML = price;
    }
}

function setAll()
{
    let addedFee = document.getElementById("select-fee");
    let selectSource = document.getElementById("select-all");

    let selectArray = document.getElementsByClassName("rates-source-value");
    let addFeeArray = document.getElementsByClassName("rates-fee-value");
    for(let i = 0; i < selectArray.length; i++)
    {
    selectArray[i].value=selectSource.value;
    addFeeArray[i].value=addedFee.value;
    changeSource(i)
    }

}

let selectArray = document.getElementsByClassName("select-rate");
for(let i = 0; i < selectArray.length; i++)
{
    selectArray[i].addEventListener("change",function(){changeSource(i);});
    changeSource(i);
}

function activeRateTab()
{
    document.getElementById("wallet-link").classList.remove("nav-link--active");
    document.getElementById("rate-link").classList.add("nav-link--active");
}

function formatInitValue()
{
    function representVal(element)
    {
        element.value = parseFloat(element.value);
        return element.value;
    }

    let rates = document.querySelectorAll('.rates-cost-value');
    rates.forEach(item => {
        representVal(item);
    });
    let fees = document.querySelectorAll('.rates-fee-value ');
    fees.forEach(item => {
        representVal(item);
    });
}

window.addEventListener('DOMContentLoaded',formatInitValue);

document.getElementById("save-rates").addEventListener("click",function(){saveRates()});

document.getElementById("set-all").addEventListener("click",function(){setAll()});

window.addEventListener('DOMContentLoaded',function(){refreshRates()});
