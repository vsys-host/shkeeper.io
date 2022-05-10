function hideElement(name)
{
    let transactionsElem = document.getElementsByClassName(name);
    for(let i = 0; i < transactionsElem.length; i++)
    {
        transactionsElem[i].classList.add("hide");
    }
}
function showElement(name)
{
    let transactionsElem = document.getElementsByClassName(name);
    for(let i = 0; i < transactionsElem.length; i++)
    {
        transactionsElem[i].classList.remove("hide");
    }
}
function defineAction(checkbox)
{
    if(checkbox.checked == true)
    {
        showElement(checkbox.name);
    }
    else
    {
        hideElement(checkbox.name);
    }
}


function hideRow(ind,type)
{
    row = document.getElementsByClassName("row-"+ind);
    for(let i = 0; i< row.length; i++)
    {
        row[i].classList.add(type);
    }
}

function showRow(ind,type)
{
    row = document.getElementsByClassName("row-"+ind);
    for(let i = 0; i< row.length; i++)
    {
        row[i].classList.remove(type);
    }
}

function filterTransactionId()
{

    let transactionInpValue = document.getElementsByName("transactionID")[0].value;
    let transactionArray = document.getElementsByClassName("transactions");

    for(let i = 1; i < transactionArray.length; i++)
    {
        transactionValue = transactionArray[i].getAttribute('value');
        if(transactionValue.indexOf(transactionInpValue) == -1)
        {
            hideRow(i,"transaction-hide");
        }
        else
        {
            showRow(i,"transaction-hide");
        }
    }
}

function filterAddress()
{
    let addressInpValue = document.getElementsByName("address-input")[0].value;
    let addressArray = document.getElementsByClassName("address");

    for(let i = 1; i < addressArray.length; i++)
    {
        addressValue = addressArray[i].getAttribute('value');
        if(addressValue.indexOf(addressInpValue) == -1)
        {
            hideRow(i,"address-hide");
        }
        else
        {
            showRow(i,"address-hide");
        }
    }
}

function filterInvoiceId()
{
    let invoiceIdValue = document.getElementsByName("invoiceID")[0].value;
    let invoiceIdArray = document.getElementsByClassName("invoice");

    for(let i = 1; i < invoiceIdArray.length; i++)
    {
        if(invoiceIdArray[i].innerHTML.indexOf(invoiceIdValue) == -1)
        {
            hideRow(i,"invoice-hide");
        }
        else
        {
            showRow(i,"invoice-hide");
        }
    }
}


function filterCoinAmount()
{
    let CoinAmountValue = document.getElementsByName("coinAmount")[0].value;
    let CoinAmountArray = document.getElementsByClassName("amount");

    for(let i = 1; i < CoinAmountArray.length; i++)
    {
        if(CoinAmountArray[i].innerHTML.indexOf(CoinAmountValue) == -1)
        {
            hideRow(i,"amount-hide");
        }
        else
        {
            showRow(i,"amount-hide");
        }
    }
}

function filterInvoiceCoin()
{
    let invoiceCoinValue = document.getElementsByName("invoiceCoin")[0].value;
    let invoiceCoinArray = document.getElementsByClassName("invoice-crpt");

    for(let i = 1; i < invoiceCoinArray.length; i++)
    {
        if(invoiceCoinArray[i].innerHTML.indexOf(invoiceCoinValue) == -1)
        {
            hideRow(i,"invoice-crpt-hide");
        }
        else
        {
            showRow(i,"invoice-crpt-hide");
        }
    }
}

function filterAmountBucks()
{
    let amountBucksValue = document.getElementsByName("dollAmount")[0].value;
    let amountBucksArray = document.getElementsByClassName("amount-bucks");

    for(let i = 1; i < amountBucksArray.length; i++)
    {
        if(amountBucksArray[i].innerHTML.indexOf(amountBucksValue) == -1)
        {
            hideRow(i,"amount-bucks-hide");
        }
        else
        {
            showRow(i,"amount-bucks-hide");
        }
    }
}

function filterStatus()
{
    let statusValueArray = document.getElementsByName("statusName")[0];
    for(let i = 1; i <= statusValueArray.length; i++)
    {
        if(statusValueArray[i].selected)
        {
            statusValue = statusValueArray[i].innerHTML;
            break;
        }
    }
    let statusArray = document.getElementsByClassName("status");
    for(let i = 1; i < statusArray.length; i++)
    {
        let statusArrayValue = statusArray[i].innerHTML.toUpperCase();
        if(statusValue.toUpperCase() == "ALL")
        {
            showRow(i,"status-hide");
        }
        else
        {
            if(statusArrayValue != statusValue.toUpperCase())
            {
                hideRow(i,"status-hide");
            }
            else
            {
                showRow(i,"status-hide");
            }
        }
    }
}

function filterCrypto()
{
    let statusValueArray = document.getElementsByName("cryptoName")[0];
    for(let i = 1; i <= 6; i++)
    {
        if(statusValueArray[i].selected)
        {
            statusValue = statusValueArray[i].innerHTML;
            break;
        }
    }
    let statusArray = document.getElementsByClassName("crypto");
    for(let i = 1; i < statusArray.length; i++)
    {
        let statusArrayValue = statusArray[i].innerHTML.toUpperCase();
        if(statusValue.toUpperCase() == "ALL")
        {
            showRow(i,"status-hide");
        }
        else
        {
            if(statusArrayValue != statusValue.toUpperCase())
            {
                hideRow(i,"status-hide");
            }
            else
            {
                showRow(i,"status-hide");
            }
        }
    }
}

function filterTime()
{
    let timeValue = document.getElementsByName("time-input")[0].value;
    let timeArray = document.getElementsByClassName("time");
    if(timeValue != "")
    {
        for(let i = 1; i < timeArray.length; i++)
        {
            if(timeArray[i].innerHTML.indexOf(timeValue) == -1)
            {
                hideRow(i,"time-hide");
            }
            else
            {
                showRow(i,"time-hide");
            }
        }
    }
    else
    {
        for(let i = 1; i < timeArray.length; i++)
        {
            showRow(i,"time-hide");
        }
    }
}

function filterInvoiceTime()
{
    let invTimeValue = document.getElementsByName("invoiceTime")[0].value;
    let timeArray = document.getElementsByClassName("inv-time");
    if(invTimeValue != "")
    {
        for(let i = 1; i < invTimeArray.length; i++)
        {
            if(invTimeArray[i].innerHTML.indexOf(invTimeValue) == -1)
            {
                hideRow(i,"inv-time-hide");
            }
            else
            {
                showRow(i,"inv-time-hide");
            }
        }
    }
    else
    {
        for(let i = 1; i < timeArray.length; i++)
        {
            showRow(i,"inv-time-hide");
        }
    }
}

function convertUnixDate()
{
    let unixtime = document.getElementsByClassName("convertDate");
    for(let i = 0; i < unixtime.length; i++)
    {
        let date = new Date(parseInt(unixtime[i].innerHTML)*1000);
        if(date != "Invalid Date")
        {
            let day = date.getDate();
            let month = date.getMonth() + 1;
            if(day < 10)
            {
                day = "0" + day;
            }
            if(month < 10)
            {
                month = "0" + month;
            }
            unixtime[i].innerHTML = day + "." + month + "." + date.getFullYear();
        }
        //unixtime[i].innerHTML = date;
    }
}

function filterDate()
{
    let dateParse = document.getElementsByName("date-input")[0].value.match(new RegExp('([0-9]+)-([0-9]+)-([0-9]+)'));
    let dateArray = document.getElementsByClassName("date");
    if(dateParse != null)
    {
        let dateValue = dateParse[3] + "." + dateParse[2] + "." + dateParse[1]; 
        for(let i = 1; i < dateArray.length; i++)
        {
            if(dateArray[i].innerHTML.indexOf(dateValue) == -1)
            {
                hideRow(i,"date-hide");
            }
            else
            {
                showRow(i,"date-hide");
            }
        }
    }
    else
    {
        for(let i = 1; i < dateArray.length; i++)
        {
            showRow(i,"date-hide");
        }
    }
}

function filterInvDate()
{
    let dateParse = document.getElementsByName("invoiceDate")[0].value.match(new RegExp('([0-9]+)-([0-9]+)-([0-9]+)'));
    let dateArray = document.getElementsByClassName("inv-date");
    if(dateParse != null)
    {
        let dateValue = dateParse[3] + "." + dateParse[2] + "." + dateParse[1]; 
        for(let i = 1; i < dateArray.length; i++)
        {
            if(dateArray[i].innerHTML.indexOf(dateValue) == -1)
            {
                hideRow(i,"inv-date-hide");
            }
            else
            {
                showRow(i,"inv-date-hide");
            }
        }
    }
    else
    {
        for(let i = 1; i < dateArray.length; i++)
        {
            showRow(i,"inv-date-hide");
        }
    }
}


let checkboxes = document.getElementsByClassName("checkbox");

for(let i = 0; i < checkboxes.length; i++)
{
    checkboxes[i].addEventListener("change",function(){defineAction(checkboxes[i])});
    defineAction(checkboxes[i]);
}

function initialCheck()
{
    formatTransAndAddresses();
    filterTransactionId();
    filterAddress();
    filterInvoiceId();
    filterCoinAmount();
    filterInvoiceCoin();
    filterAmountBucks();
    filterStatus();
    filterTime();
    filterCrypto();
    filterInvoiceTime();
    filterDate();
    filterInvDate();
}

function formatTransAndAddresses()
{
    let transactions = document.querySelectorAll('.transactions-val');
    let addresses = document.querySelectorAll('.address-val');

    addresses.forEach( item => {
        formatOutputText(item);
        item.addEventListener('click',function(){
            copyToBuffer(item)
        });
    });

    transactions.forEach( item => {
        formatOutputText(item);
        item.addEventListener('click',function(){
            copyToBuffer(item)
        });
    });

    function formatOutputText(element)
    {
        let value =element.getAttribute('value');
        let strLength = value.length;
        let startSubStr = value.substring(0,6);
        let endSubStr = value.substring(strLength-4,strLength);
        element.innerHTML =  startSubStr + "..." + endSubStr;
        var tooltip = new bootstrap.Tooltip(element)        
    }

    function copyToBuffer(element)
    {
        let value =element.getAttribute('value');
        copyTextToClipboard(value);

        try {
            var successful = document.execCommand('copy');
            var msg = successful ? 'successful' : 'unsuccessful';
            console.log('Copying text command was ' + msg);
        } catch (err) {
            console.log('Oops, unable to copy');
        }
        function fallbackCopyTextToClipboard(text) {
            var textArea = document.createElement("textarea");
            textArea.value = text;
            
            // Avoid scrolling to bottom
            textArea.style.top = "0";
            textArea.style.left = "0";
            textArea.style.position = "fixed";
            
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();
            
            try {
                var successful = document.execCommand('copy');
                var msg = successful ? 'successful' : 'unsuccessful';
                console.log('Fallback: Copying text command was ' + msg);
            } catch (err) {
                console.error('Fallback: Oops, unable to copy', err);
            }
            
            document.body.removeChild(textArea);
        }
        function copyTextToClipboard(text) {
            if (!navigator.clipboard) {
                fallbackCopyTextToClipboard(text);
                return;
            }
            navigator.clipboard.writeText(text).then(function() {
                console.log('Async: Copying to clipboard was successful!');
            }, function(err) {
                console.error('Async: Could not copy text: ', err);
            });
        }
    }
    


}

document.getElementsByName("transactionID")[0].addEventListener("keyup", function(){filterTransactionId()});
document.getElementsByName("address-input")[0].addEventListener("keyup", function(){filterAddress()});
document.getElementsByName("invoiceID")[0].addEventListener("keyup", function(){filterInvoiceId()});
document.getElementsByName("coinAmount")[0].addEventListener("keyup", function(){filterCoinAmount()});
document.getElementsByName("invoiceCoin")[0].addEventListener("keyup", function(){filterInvoiceCoin()});
document.getElementsByName("dollAmount")[0].addEventListener("keyup", function(){filterAmountBucks()});
document.getElementsByName("statusName")[0].addEventListener("change", function(){filterStatus()});
document.getElementsByName("cryptoName")[0].addEventListener("change", function(){filterCrypto()});
document.getElementsByName("time-input")[0].addEventListener("change", function(){filterTime()});
document.getElementsByName("invoiceTime")[0].addEventListener("change", function(){filterInvoiceTime()});
document.getElementsByName("date-input")[0].addEventListener("change", function(){filterDate()});
document.getElementsByName("invoiceDate")[0].addEventListener("change", function(){filterInvDate()});
window.addEventListener('DOMContentLoaded',function(){
    convertUnixDate();
    initialCheck();
});


